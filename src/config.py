import os

def get(name):
    value = os.getenv(name)
    return value

def ensure(name):
    value = os.getenv(name)
    if not value:
        raise Exception(f"Env Var '{name}' is required!")
    return value
