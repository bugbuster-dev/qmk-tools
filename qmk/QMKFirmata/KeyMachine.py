import keyboard, sched, threading, os, time, re

from DebugTracer import DebugTracer

class KeyMachine:

    def __init__(self, keyb):
        self.dbg = DebugTracer(zones={
            "DEBUG": 0,
            "REPEAT": 0,
            "COMBO": 0,
            "SEQ": 0,
            "MORSE": 0,
        }, obj=self)

        self.dbg.tr('DEBUG', f"KeyMachine: {keyb}")
        self.keyb = keyb
        try:
            self.key_layout = keyb.keyboardModel.KEY_LAYOUT['win']
        except:
            self.key_layout = None
        self.key_event_stack = [] #todo remove if not needed
        self.key_pressed = {}
        self.combos = {}
        self.sequences = {}

        self.key_repeat_delay = 0.5
        self.key_repeat_time = 0.05
        self.key_repeat_scheduler = sched.scheduler(time.time, time.sleep)
        self.key_repeat_sched_event = None

        self.sequence_handler_scheduler = sched.scheduler(time.time, time.sleep)
        self.sequence_handler_sched_event = None

        self.morse_handler_scheduler = sched.scheduler(time.time, time.sleep)
        self.morse_handler_sched_event = None
        self.morse_tap_stack = []

        try:
            # uncomment to enable beep on morse key press
            #from pysinewave import SineWave
            self.morse_beep = SineWave(pitch = 14, pitch_per_second = 10, decibels=-200, decibels_per_second=10000)
            self.morse_beep.play()
        except:
            self.morse_beep = None

        devel_test = True
        if devel_test:
            def on_test_combo1():
                keyboard.write(u"hello äçξضяשå両めษᆆऔጩᗗ¿")

            def on_test_combo_leader():
                keyboard.write("leader key todo")

            def on_test_sequence():
                keyboard.write("hello hello hello")

            def on_windows_lock():
                os.system("rundll32.exe user32.dll,LockWorkStation")

            def on_test_sequence_1():
                keyboard.write("pam pam")

            def on_test_sequence_tap_1():
                keyboard.write("1st tap")
            def on_test_sequence_tap_2():
                keyboard.write("2nd tap")
            def on_test_sequence_tap_4():
                keyboard.write("all tapped!")

            self.register_combo(['left ctrl','left menu','space','m'], on_test_combo1)
            self.register_combo(['fn',';'], on_test_combo_leader)
            self.register_combo(['left windows','l'], on_windows_lock)

            self.register_sequence(['1','2','3'], [(0,300), (0,300)], on_test_sequence)
            self.register_sequence(['pause','pause','pause','pause'], [(0,300), (0,300), (0,300)], [ on_test_sequence_tap_1, on_test_sequence_tap_2, None, on_test_sequence_tap_4])
            self.register_sequence(['right','right','right','right','right'], [(350,500), (100,250), (100,250), (300,450)], on_test_sequence_1)

    def control_pressed(self):
        return self.key_pressed.get('left ctrl', 0) or self.key_pressed.get('ctrl', 0)

    def shift_pressed(self):
        return self.key_pressed.get('left shift', 0) or self.key_pressed.get('right shift', 0)

    def alt_pressed(self):
        return self.key_pressed.get('left menu', 0) or self.key_pressed.get('right menu', 0)

    def win_pressed(self):
        return self.key_pressed.get('left windows', 0) or self.key_pressed.get('right windows', 0)

    def fn_pressed(self):
        return self.key_pressed.get('fn', 0)

    def is_mod_key(self, key):
        return key.endswith('ctrl') or key.endswith('shift') or key.endswith('menu') or key.endswith('windows') or key == 'fn'

    def mod_keys_pressed(self):
        pressed = []
        if self.win_pressed():
            pressed.append('left windows')
        if self.alt_pressed():
            pressed.append('alt')
        if self.control_pressed():
            pressed.append('ctrl')
        if self.shift_pressed():
            pressed.append('shift')
        if self.fn_pressed():
            pressed.append('fn')
        return pressed

    def register_combo(self, keys, handler):
        combo_keys = "+".join(keys)
        self.combos[combo_keys] = (keys, handler)
        self.dbg.tr('COMBO', f"register_combo: {combo_keys}, {keys}, {handler}")

    # todo: flags/options[] to define behavior for different "sequence types" (leader key, tap dance, ...)
    # - can define state change on key press/hold/release on each "sequence step"
    def register_sequence(self, keys, timeout, handler, flags=[]):
        sequence_keys = "+".join(keys)
        self.sequences[sequence_keys] = (keys, timeout, (0, 0), handler, flags) # sequence state: (index, time)
        self.dbg.tr('SEQ', f"register_sequence: {sequence_keys}, {keys}, {timeout}, {handler}, {flags}")

    @staticmethod
    def time_elapsed(time_begin, time_end):
        time_diff = time_end - time_begin
        if time_diff < 0:
            time_diff = 65536 + time_diff
        return time_diff

    # todo: leader key, tap dance, ...
    def process_sequences(self, key, time, pressed):
        if pressed:
            for _key, seq_handler in self.sequences.items():
                sequence_keys = seq_handler[0]
                timeout = seq_handler[1]
                state = seq_handler[2]
                handler = seq_handler[3]
                state_index = state[0]
                state_time = state[1]
                try:
                    if key == sequence_keys[state_index]:
                        self.dbg.tr('SEQ', f"process_sequences: {key}, {sequence_keys}, {state}")
                        if state_index > 0:
                            time_diff = self.time_elapsed(state_time, time)
                            if time_diff > timeout[state_index-1][1] or time_diff < timeout[state_index-1][0]:
                                self.dbg.tr('SEQ', f"process_sequences: keypress time: {time_diff} out of range {timeout[state_index-1]}")
                                break

                        try:
                            self.sequence_handler_scheduler.cancel(self.sequence_handler_sched_event)
                        except:
                            pass

                        if type(handler) == list:
                            handler_fn = handler[state_index]
                            # schedule handler call if not last
                            if handler_fn and state_index < len(handler)-1:
                                self.run_sequence_handler(handler_fn, timeout[state_index][1]/1000)
                        else:
                            handler_fn = handler

                        state_index += 1
                        state = (state_index, time)
                        if state_index == len(sequence_keys):
                            self.dbg.tr('SEQ', f"sequence! call handler: {handler_fn}")
                            self.sequences[_key] = (sequence_keys, timeout, (0, 0), handler)
                            handler_fn()
                            return True
                        self.sequences[_key] = (sequence_keys, timeout, state, handler)
                        return False
                except:
                    pass

            # key press does not match any sequence, reset all sequences
            for _key, seq_handler in self.sequences.items():
                self.sequences[_key] = (seq_handler[0], seq_handler[1], (0, 0), seq_handler[3])

        return False

    def process_combos(self, key, time, pressed):
        if len(self.key_pressed) == 0:
            return False

        if pressed:
            for _, combo_handler in self.combos.items():
                combo_keys = combo_handler[0]
                handler = combo_handler[1]
                self.dbg.tr('COMBO', f"process_combos: {combo_handler}")
                try:
                    if combo_keys[-1] == key:
                        self.dbg.tr('COMBO', f"process_combos: {combo_keys}")
                        if all([self.key_pressed.get(k, 0) for k in combo_keys[:-1]]):
                            self.dbg.tr('COMBO', f"combo!")
                            handler()
                            return True
                except:
                    pass
        return False

    def repeat_needed(self, key):
        if self.is_mod_key(key):
            return False
        if key == 'morse':
            return False
        return True

    def key_repeat_sched_fn(self, key):
        self.dbg.tr('REPEAT', f"key_repeat_sched_fn: {key}")
        if key in self.key_pressed: # may race with key_event, only read dict no lock needed
            keyboard.press(key)
            self.run_repeat(key, self.key_repeat_time)

    def sequence_handle_sched_fn(self, handler):
        self.dbg.tr('SEQ', f"sequence_handle_sched_fn: {handler}")
        handler()

    def process_workarounds(self, press_keys):
        # workaround for '_', '?', ':'
        if len(press_keys) == 2:
            if press_keys[0].endswith('shift'):
                check_shift_combo = press_keys.copy()
                check_shift_combo[0] = 'shift'

                combine = [ (['shift','-'], '_'), (['shift','/'], '?'), (['shift',';'], ':')]
                for combo in combine:
                    if check_shift_combo == combo[0]:
                        keyboard.press(combo[1])
                        press_keys = []
        return press_keys

    def morse_handle_timeout(self):
        #self.dbg.tr('MORSE', f"morse_handle_timeout")
        def morse_get_char(tap_stack):
            morse_code = {
                '.-': 'A', '-...': 'B', '-.-.': 'C', '-..': 'D', '.': 'E', '..-.': 'F',
                '--.': 'G', '....': 'H', '..': 'I', '.---': 'J', '-.-': 'K', '.-..': 'L',
                '--': 'M', '-.': 'N', '---': 'O', '.--.': 'P', '--.-': 'Q', '.-.': 'R',
                '...': 'S', '-': 'T', '..-': 'U', '...-': 'V', '.--': 'W', '-..-': 'X',
                '-.--': 'Y', '--..': 'Z',
                '.----': '1', '..---': '2', '...--': '3', '....-': '4', '.....': '5',
                '-....': '6', '--...': '7', '---..': '8', '----.': '9', '-----': '0',
                '...---...': 'SOS',
            }
            morse = ''.join([tap[0] for tap in tap_stack])
            if morse in morse_code:
                return morse_code[morse]
            return ''

        char = None
        if len(self.morse_tap_stack) > 0:
            char = morse_get_char(self.morse_tap_stack)
            self.morse_tap_stack = []
        self.dbg.tr('MORSE', f"morse: {char}")
        keyboard.write(' ')

    def handle_morse_key(self, key, time, pressed):
        # https://morsecode.world/international/timing.html
        DIT_DURATION    = 150
        DAH_DURATION    = 3*DIT_DURATION
        SPACE_DIT_DAH   = 1*DIT_DURATION
        SPACING_FACTOR  = 1
        SPACE_CHAR      = int(3*DIT_DURATION*SPACING_FACTOR)
        SPACE_WORD      = int(7*DIT_DURATION*SPACING_FACTOR)

        if self.morse_handler_sched_event:
            try:
                self.morse_handler_scheduler.cancel(self.morse_handler_sched_event)
            except:
                pass
            self.morse_handler_sched_event = None

        if pressed:
            if self.morse_beep:
                self.morse_beep.set_volume(-60)
            self.key_pressed[key] = time
        else:
            if self.morse_beep:
                self.morse_beep.set_volume(-200)

            press_duration = self.time_elapsed(self.key_pressed[key], time)
            dit_dah = '-'
            if press_duration < DIT_DURATION:
                dit_dah = '.'

            if len(self.morse_tap_stack) > 0:
                last_tap = self.morse_tap_stack[-1]
                last_tap_release_time = last_tap[2]
            else:
                last_tap_release_time = 0

            space_time_didah = self.time_elapsed(last_tap_release_time, self.key_pressed[key])
            self.dbg.tr('MORSE', f"morse: {dit_dah} ({space_time_didah}, {press_duration} ms)")
            self.morse_tap_stack.append((dit_dah, self.key_pressed[key], time))
            try:
                keyboard.write(dit_dah)
            except:
                pass

            if key in self.key_pressed:
                del self.key_pressed[key]

            self.run_morse_timeout(SPACE_CHAR/1000)

    def key_event(self, row, col, time, pressed):
        try:
            key = self.key_layout[row][col]
            self.dbg.tr('DEBUG', f"key_event: {row}, {col}, {time}, {pressed} -> {key}")
        except:
            self.dbg.tr('DEBUG', f"key_event: {row}, {col}, {time}, {pressed} -> not mapped")
            return

        if key == 'morse':
            self.handle_morse_key(key, time, pressed)
            return

        if pressed:
            press_keys = []
            pressed_mods = self.mod_keys_pressed()
            for mod in pressed_mods:
                self.dbg.tr('DEBUG', f"mod key: {mod}")
                press_keys.append(mod)
            press_keys.append(key)
            press_keys = self.process_workarounds(press_keys)
            for key in press_keys:
                try:
                    self.dbg.tr('DEBUG', f"press key: {key}")
                    keyboard.press(key)
                except:
                    pass

        self.process_combos(key, time, pressed)
        self.process_sequences(key, time, pressed)

        if pressed:
            self.key_pressed[key] = time
            self.dbg.tr('DEBUG', f"key pressed: {self.key_pressed}")
            if len(self.key_pressed) == 1:
                if self.repeat_needed(key):
                    self.dbg.tr('DEBUG', f"schedule repeat: {key}")
                    self.run_repeat(key, self.key_repeat_delay)
        else:
            if key in self.key_pressed:
                del self.key_pressed[key]
                if len(self.key_pressed) == 0:
                    try:
                        self.key_repeat_scheduler.cancel(self.key_repeat_sched_event)
                        self.key_repeat_sched_event = None
                        self.dbg.tr('DEBUG', f"schedule repeat canceled: {key}")
                    except:
                        pass
            try:
                keyboard.release(key)
            except:
                pass

        # push on key event stack
        self.key_event_stack.append((((row, col), time, pressed), key))
        if len(self.key_event_stack) > 100:
            self.key_event_stack.pop(0)

    def run_repeat(self, key, time):
        self.dbg.tr('REPEAT', f"run_repeat: {key}, {time}")
        def run_repeat_schedule_fn(key):
            self.key_repeat_sched_event = self.key_repeat_scheduler.enter(time, 1, self.key_repeat_sched_fn, (key,))
            self.key_repeat_scheduler.run()
        threading.Thread(target=run_repeat_schedule_fn, args=(key,)).start()

    def run_sequence_handler(self, handler, time):
        self.dbg.tr('SEQ', f"run_sequence_handler: {time}")
        def run_sequence_handle_schedule_fn(handler):
            self.sequence_handler_sched_event = self.sequence_handler_scheduler.enter(time, 1, self.sequence_handle_sched_fn, (handler,))
            self.sequence_handler_scheduler.run()
        threading.Thread(target=run_sequence_handle_schedule_fn, args=(handler,)).start()

    def run_morse_timeout(self, time):
        #self.dbg.tr('MORSE', f"run_morse_timeout: {time}")
        def run_morse_timeout_schedule_fn():
            self.morse_handler_sched_event = self.morse_handler_scheduler.enter(time, 1, self.morse_handle_timeout)
            self.morse_handler_scheduler.run()
        threading.Thread(target=run_morse_timeout_schedule_fn).start()
