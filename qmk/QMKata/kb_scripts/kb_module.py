source = "module_examples/combo_layer_filter.c"
slot_id = 4

print(f"building {source}")
result = kb.build_module(source)
print(result)
if not result:
    print("build failed")
    raise SystemExit(1)

print(f"build ok: size={result['size']} hooks={result['hooks']}")
print("note: slot 4 shares a flash sector with slots 5-7")

ok = kb.load_module(slot_id, result)
print(f"load slot {slot_id}: {ok}")
