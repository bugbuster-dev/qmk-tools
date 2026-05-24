# Plan: Fix the sticky-combo SRAM module

> **Status: RESOLVED** — Merged to `main` (QMKata) and `2025q3_q3_max` (firmware).
> All 8 gtests pass. Verified on hardware.

This document captures the remaining work needed to make the
`module_examples/pipeline_sticky_combo/` example actually behave like a
sticky combo (arm on simultaneous press, then act on follow-up taps
and releases) instead of leaking the first key to the host and never
recovering.

The SRAM **loader** is working as of `e8ccff6` on `feat/sram-modules` /
`44b94a7c25` on `2025q3_q3_max` — the bug below is purely in the module's
own state-machine logic and is also present in the firmware-built
adapter (`quantum/features/sticky_combo_adapter.c`), so fixing it here
should be mirrored there or vice-versa.

If you only want to read the loader compilation story, see
`sram-module-compilation.md`. This document assumes that loader works.

## Observed misbehavior

Combo def: `{ KC_J, KC_K, KC_NO, KC_UP, KC_DOWN }` — J + K within 50ms
should arm. Then hold K and tap J → ↑; hold J and tap K → ↓.

What actually happens in a text editor:

| Step | User action | Observed |
|---|---|---|
| 1 | Press J, press K within 50ms, release both | "j" is typed (no arrow), and J appears to stick — host receives a J that is never released → key repeat fires forever |
| 2 | Try anything to recover | Only releasing J again (re-press + release) clears the stuck state |

Console trace from the working build (`pipe[0]:` lines from firmware
diag, `stick:` lines were a temporary trace in the module):

```
stick: kc=0x000d p=1 state=4    ← J press, state IDLE
stick: kc=0x000e p=1 state=4    ← K press, still IDLE at entry — but
                                  this call sees the pending J and
                                  transitions to ARMED_BOTH (state 1)
stick: kc=0x000d p=0 state=1    ← J release, now ARMED_BOTH
stick: kc=0x000e p=0 state=3    ← K release, ARMED_FOR_KEY2 — wrong
                                  state for a simple disarm
```

## Root cause

Look at `sticky_handle()` in `sticky_combo_module.c`:

```c
/* IDLE */
if (st->sm.state_id == StickyCombo_StateId_IDLE) {
    if (!event->pressed) return SM_PASS;

    bool is_key1 = false, is_key2 = false;
    int8_t combo = find_combo_for_key(kc, &is_key1, &is_key2);
    if (combo < 0) return SM_PASS;

    if (st->pending_combo == combo && /* …simultaneous… */) {
        /* …arm combo, consume K press… */
        return SM_CONSUME;
    }

    /* Not simultaneous yet — record J and let it through. */
    st->pending_combo = combo;
    st->pending_is_key1 = is_key1;
    st->pending_time = env->timer_read();
    return SM_PASS;            /* ←← BUG */
}
```

The handler does not know at the moment of the J press whether K will
follow within 50ms. So it does the wrong thing: it returns `SM_PASS`,
which lets the firmware forward the J press to the host *immediately*.

If K then arrives within the window, the module arms the combo and
consumes the K press — but the J press has already been delivered.
J then gets released later via the ARMED_BOTH path, where
`return SM_CONSUME` swallows the *release* too. The host's view is
therefore:

```
J press   ← delivered (because we returned SM_PASS)
K press   ← consumed by module
J release ← consumed by module (BUG)
K release ← consumed by module
```

→ J appears to be held forever → key repeat → continuous J.

## What the fix has to do

Defer the J press by exactly `STICKY_COMBO_WINDOW_MS` (currently 50 ms)
so that we know whether K will follow before committing. Three outcomes:

| Outcome inside the window | Action |
|---|---|
| K press for the same combo arrives | Discard the buffered J press entirely (arm combo, optionally fire `combo_action`). Original J press never reaches the host. |
| Window expires with no K | Replay the J press to the host now (a real, normal J keydown), then on J release pass the release through normally. |
| User presses a third, non-combo key | Same as "window expires" — flush the pending J first, then forward the third key. |

The release of J inside the window also needs handling: if the user
taps and releases J faster than 50 ms, the combo never armed and we
need to deliver the press+release pair as a normal short tap.

## Design options

### Option A — `tick()`-driven flush (recommended)

Use the existing `pipeline_tick()` callback (`g_machine.tick`, runs
every matrix scan) to time the pending press out and flush it
synthetically via `env->tap_code16(pending_kc)` or
`env->register_code16(pending_kc)` followed by `unregister_code16` on
release.

Pros:
* Uses infrastructure that already exists in `pipeline_env_t`
  (`timer_read`, `timer_elapsed`, `tap_code16`,
  `register_code16` / `unregister_code16`).
* No firmware changes required.
* Symmetric with the existing "clear stale pending" logic that the
  firmware adapter already runs in its tick path
  (`sticky_combo_adapter.c:166–169`).

Cons:
* `tap_code16` issues a press + release on the next scan; it does not
  preserve the original press / release boundaries (so chord presses
  *after* a combo decision still have minor timing skew on the order
  of one matrix scan).
* If the user presses J and starts holding it for a long time (longer
  than the window) before pressing anything else, the firmware will
  see a `tap_code16` (brief press) followed by … nothing, because the
  module is now holding the *original* press internally. We need to
  upgrade `tap_code16(kc)` to `register_code16(kc)` + remember that
  "kc is currently held on the host side" so we can unregister it
  cleanly on the eventual J release.

Sketch:

```c
typedef struct {
    /* …existing fields… */
    bool     pending_pressed_on_host;  /* did we register_code16 yet? */
} sticky_state_t;

/* sticky_tick — called every matrix scan */
static void sticky_tick(void *self) {
    sticky_state_t *st = self;
    if (st->pending_combo < 0) return;
    if (st->env->timer_elapsed(st->pending_time) <= STICKY_COMBO_WINDOW_MS) return;

    /* Window expired without the partner key. Commit the buffered press. */
    uint16_t kc = (st->pending_is_key1
                   ? module_sticky_combos[st->pending_combo].key1
                   : module_sticky_combos[st->pending_combo].key2);
    st->env->register_code16(kc);
    st->pending_pressed_on_host = true;
    /* Keep pending_combo set so the eventual release knows what to do. */
}

/* sticky_handle, IDLE branch */
if (event->pressed) {
    /* …existing simultaneous-press detection (consumes K, kills pending)… */
    /* If we already have a pending and now see a *third*, non-combo key:
       flush pending press, then pass the third key. */
    if (st->pending_combo >= 0 && /* third key */) {
        if (!st->pending_pressed_on_host) {
            uint16_t pkc = …;
            st->env->register_code16(pkc);
            st->pending_pressed_on_host = true;
        }
        st->pending_combo = -1;
        return SM_PASS;
    }
    /* Otherwise start a new pending and CONSUME — do not let J through yet. */
    st->pending_combo = combo;
    st->pending_is_key1 = is_key1;
    st->pending_time = st->env->timer_read();
    st->pending_pressed_on_host = false;
    return SM_CONSUME;   /* ←← was SM_PASS — this is the fix */
}

/* Release of the same key while still pending */
if (!event->pressed && st->pending_combo >= 0 && /* kc matches pending */) {
    if (st->pending_pressed_on_host) {
        st->env->unregister_code16(/*kc*/);
        st->pending_pressed_on_host = false;
    } else {
        /* Tap shorter than the window — synthesise a full tap. */
        st->env->tap_code16(/*kc*/);
    }
    st->pending_combo = -1;
    return SM_CONSUME;
}
```

### Option B — pre-tap consume + replay through `tap_code16`

Same outcome but without using `tick()`: when the window has passed
without a partner key, the *next* event flowing through `handle()`
flushes the buffered press first. This avoids needing the
`pending_pressed_on_host` register/unregister bookkeeping but has a
worse worst case: if the user presses J and *only* J for a long time,
the J press never appears on the host until they touch the next key.
Not acceptable.

### Option C — extend `pipeline_env_t` with `defer_event(record, ms)`

Push the responsibility into the firmware: the module says "I'll
decide later, ask me again in 50 ms", and the firmware buffers the
keyrecord and re-injects it if no decision came in by then. Cleanest
semantically but requires a non-trivial firmware feature, a v-bump on
`pipeline_env_t`, and equivalent rework in the firmware's own combo
adapter. Out of scope for the example module fix.

## Recommended implementation order

1. **Mirror the firmware bug.** Reproduce the same misbehavior with
   the firmware-built `quantum/features/sticky_combo_adapter.c` (set
   `MODULE_BUILTIN_STICKY_COMBO_ENABLE = yes`, drop the SRAM module).
   Confirm it does the same thing. This rules out an SRAM-specific
   issue and gives us a second test target.
2. **Fix the firmware adapter first** using Option A. It has the
   simpler build / test loop (no relocation, no upload). Verify in a
   text editor.
3. **Port the fix to `sticky_combo_module.c`.** The diff should be
   small — both files share the same state-machine skeleton. Rebuild
   the SRAM module via QMKata, upload to slot 8, verify.
4. **Update `combos_def.h` demo entry** if desired — the `KC_NO`
   `combo_action` makes the arm event silent, which is fine for J+K
   → arrows but confusing during testing. Consider setting
   `combo_action = KC_DOWN` temporarily to make arming audible / visible.
5. **Add a regression test** to `test_module_api_contract.py` or a
   new file: simulate a `pipeline_env_t` in Python, feed it a sequence
   of `keyevent_t` / `keyrecord_t` structures, and assert on the
   sequence of synthesised tap / register / unregister calls. The
   module's pure state-machine logic is testable without hardware.

## Files to touch

| File | Change |
|---|---|
| `qmk-tools/qmk/QMKata/module_examples/pipeline_sticky_combo/sticky_combo_module.c` | `sticky_handle()` IDLE branch returns `SM_CONSUME`, new `pending_pressed_on_host` field, new logic in `sticky_tick()` to flush after window, release path that emits `tap_code16` or `unregister_code16` |
| `qmk-tools/qmk/QMKata/module_examples/pipeline_sticky_combo/combos_def.h` | optional: change demo `combo_action` to make arm observable during testing |
| `keychron_qmk_firmware_emulator/quantum/features/sticky_combo_adapter.c` | same fix, kept in lockstep with the SRAM example |
| `qmk-tools/qmk/QMKata/test_module_api_contract.py` (new tests) | unit-test the state-machine transitions and env-call sequences |

## Verification checklist

After applying the fix, in a text editor with the module loaded into
SRAM slot 8, these sequences must produce the indicated output and
**no continuous key repeat**:

* Press J, wait > 50 ms, release J → host receives a single `j`.
* Press J, press K within 50 ms, release both → arm; host receives
  nothing (because demo `combo_action == KC_NO`).
* Press J + K to arm; hold K, tap J → host receives ↑.
* Press J + K to arm; hold J, tap K → host receives ↓.
* Press J + K to arm; release both → host receives nothing extra.
* Press J + K to arm; press a third key (e.g. L) → third key flushes
  through normally, combo disarms cleanly.
* Press J, immediately press L (not a combo key) → J + L should both
  appear in order; pending state cleared.

Each scenario also has to work when J / K is held long enough to
trigger normal key repeat — the firmware key-repeat timer should
treat the synthesised press exactly like a real one (which means we
must use `register_code16` rather than `tap_code16` for the
window-expired flush).

## Related

* `sram-module-compilation.md` — the loader story (already done).
* `quantum/features/sticky_combo.puml` — the StateSmith UML for the
  state machine. The pending-press buffering is an *external* shim
  around it; the generated `StickyCombo.c` does not need changes.
* `module_api.h` — `pipeline_env_t` already exposes everything Option A
  needs (`timer_read`, `timer_elapsed`, `tap_code16`, `register_code16`,
  `unregister_code16`).
