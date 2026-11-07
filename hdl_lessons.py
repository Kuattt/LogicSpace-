"""Local teacher-authored HDL/circuit lessons with behavior-based grading."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

from engine import Circuit
from hdl_model import run_circuit_vectors, run_vectors
from project_experience import APP_DATA, _atomic_json
from tutorials import LessonResult


class CustomLessonStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else APP_DATA / "hdl_lessons"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, lesson_id, title, description, task, vectors, starter=None, source=""):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", lesson_id):
            raise ValueError("Lesson ID must use letters, digits, underscore or dash")
        if not all(isinstance(value, str) and value.strip() for value in (title, description, task)):
            raise ValueError("Lesson needs a title, description and task")
        if not isinstance(source, str) or not isinstance(vectors, list) or not vectors or len(vectors) > 200:
            raise ValueError("Lesson needs 1–200 test vectors")
        for vector in vectors:
            if (not isinstance(vector, dict) or not isinstance(vector.get("inputs"), dict)
                    or not isinstance(vector.get("expected"), dict) or not vector["expected"]):
                raise ValueError("Each vector needs inputs and expected outputs")
            if any(value is not None and (type(value) is not int or value < 0)
                   for value in (*vector["inputs"].values(), *vector["expected"].values())):
                raise ValueError("Vector values must be nonnegative integers or null for X")
        circuit = starter.to_dict() if isinstance(starter, Circuit) else None
        if circuit is not None: Circuit.from_dict(circuit)
        item = {"format": "logicspace-hdl-lesson", "version": 1, "id": lesson_id,
                "title": title.strip(), "description": description.strip(), "task": task.strip(),
                "vectors": deepcopy(vectors), "starter": circuit, "source": source}
        _atomic_json(self.root / (lesson_id + ".json"), item)
        return item

    def load(self, lesson_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", lesson_id): raise ValueError("Invalid lesson ID")
        item = json.loads((self.root / (lesson_id + ".json")).read_text(encoding="utf-8"))
        if (not isinstance(item, dict) or item.get("format") != "logicspace-hdl-lesson"
                or item.get("version") != 1 or item.get("id") != lesson_id
                or not isinstance(item.get("vectors"), list) or not item["vectors"]
                or len(item["vectors"]) > 200
                or any(not isinstance(item.get(key), str) for key in ("title", "description", "task", "source"))):
            raise ValueError("Invalid HDL lesson file")
        for vector in item["vectors"]:
            if (not isinstance(vector, dict) or not isinstance(vector.get("inputs"), dict)
                    or not isinstance(vector.get("expected"), dict) or not vector["expected"]
                    or any(value is not None and (type(value) is not int or value < 0)
                           for value in (*vector["inputs"].values(), *vector["expected"].values()))):
                raise ValueError("Invalid HDL lesson vectors")
        if item.get("starter") is not None: Circuit.from_dict(item["starter"])
        return item

    def list(self):
        result = []
        for path in sorted(self.root.glob("*.json")):
            try: result.append(self.load(path.stem))
            except (ValueError, KeyError, TypeError, json.JSONDecodeError): continue
        return result

    def delete(self, lesson_id):
        self.load(lesson_id)
        (self.root / (lesson_id + ".json")).unlink()

    def check(self, lesson_id, circuit=None, source=""):
        item = self.load(lesson_id)
        try:
            if not source.strip() and circuit is None:
                raise ValueError("A circuit or HDL source is required for grading")
            results = (run_vectors(source, item["vectors"]) if source.strip() else
                       run_circuit_vectors(circuit, item["vectors"]))
            failed = next((row for row in results if not row["passed"]), None)
            if failed:
                raise ValueError(f"Vector {failed['step']}: expected {failed['expected']}, actual {failed['actual']}")
            return LessonResult(True, f"Passed {len(results)} simulation vectors.", len(results))
        except (ValueError, TypeError, KeyError, IndexError) as error:
            return LessonResult(False, str(error), 0)
