"""
Lance les tests unitaires (tests/) et écrit un rapport JUnit pour Jenkins,
sans dépendance supplémentaire. Code de sortie 1 si un test échoue.

    python scripts/ci_tests.py --rapport rapports-ci
"""
from __future__ import annotations

import argparse
import sys
import time
import unittest
from pathlib import Path
from xml.sax.saxutils import escape

RACINE = Path(__file__).resolve().parent.parent


class ResultatJUnit(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cas: list[tuple[str, str, float, str | None, str | None]] = []
        self._debut = 0.0

    def startTest(self, test):
        self._debut = time.monotonic()
        super().startTest(test)

    def _noter(self, test, genre=None, detail=None):
        classe, _, nom = test.id().rpartition(".")
        self.cas.append((classe, nom, time.monotonic() - self._debut, genre, detail))

    def addSuccess(self, test):
        super().addSuccess(test)
        self._noter(test)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._noter(test, "failure", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._noter(test, "error", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._noter(test, "skipped", reason)


def ecrire(resultat: ResultatJUnit, chemin: Path) -> None:
    attr = {'"': "&quot;"}
    lignes = []
    for classe, nom, duree, genre, detail in resultat.cas:
        cas = f'<testcase classname="{escape(classe, attr)}" name="{escape(nom, attr)}" time="{duree:.3f}">'
        if genre == "skipped":
            cas += f'<skipped message="{escape(detail or "", attr)}"/>'
        elif genre:
            cas += f'<{genre} message="{escape((detail or "").strip().splitlines()[-1][:300], attr)}">{escape(detail or "")}</{genre}>'
        lignes.append(cas + "</testcase>")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<testsuite name="Tests Python" tests="{resultat.testsRun}" '
        f'failures="{len(resultat.failures)}" errors="{len(resultat.errors)}" skipped="{len(resultat.skipped)}">\n'
        + "\n".join(lignes) + "\n</testsuite>\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rapport", type=Path, default=RACINE / "rapports-ci")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(RACINE / "tests"), top_level_dir=str(RACINE / "tests"))
    resultat = unittest.TextTestRunner(resultclass=ResultatJUnit, verbosity=1).run(suite)
    ecrire(resultat, args.rapport / "tests-python.xml")
    return 0 if resultat.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
