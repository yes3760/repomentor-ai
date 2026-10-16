import pickle
import yaml


def yukle(dosya):
    with open(dosya, "rb") as f:
        return pickle.load(f)


def ayar_oku(yol):
    with open(yol) as f:
        return yaml.load(f)


def l(x):
    if x == None:
        return 0
    return len(x)
