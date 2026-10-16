"""DEMO: RepoMentor PR incelemesinin kalite kapısını sınamak için bilerek riskli kod; birleştirilmeyecek."""

import os


def calculate() -> int:
    """Evaluate an expression the user typed."""
    return eval(input("İfade: "))


def list_folder() -> None:
    """List a folder the user names."""
    os.system("ls " + input("Klasör: "))
