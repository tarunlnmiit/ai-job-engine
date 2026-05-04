import ollama
try:
    models = ollama.list()
    print("Full response type:", type(models))
    print("Full response:", models)
    if hasattr(models, 'models'):
        for m in models.models:
            print("Model object:", m)
            # Try to find the name
            if hasattr(m, 'model'):
                print("Name via .model:", m.model)
            elif isinstance(m, dict) and 'name' in m:
                print("Name via ['name']:", m['name'])
            elif isinstance(m, dict) and 'model' in m:
                print("Name via ['model']:", m['model'])
except Exception as e:
    print("Error:", e)
