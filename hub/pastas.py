"""As pastas de cada pessoa (fase 16): quem cuida de qual pasta, para as prioridades do mês.

Um administrador liga cada analista (ou gestor) às pastas de que ele cuida, na página Pessoas. Uma
pasta pode ter mais de uma pessoa, e uma pessoa pode ter várias pastas. Assistente não tem pasta.
"""

from datetime import datetime

from .db import Database, log_event
from .demands import FOLDERS
from .people import Person, ValidationError, list_people


def folders_by_person(db: Database) -> dict[int, tuple[str, ...]]:
    """As pastas de cada pessoa, na ordem A a G (quem não tem pasta fica de fora)."""
    with db.connect() as conn:
        rows = conn.execute("SELECT person_id, folder FROM person_folders").fetchall()
    mine: dict[int, set[str]] = {}
    for r in rows:
        mine.setdefault(r["person_id"], set()).add(r["folder"])
    return {pid: tuple(f for f in FOLDERS if f in fs) for pid, fs in mine.items()}


def folders_of(db: Database, person_id: int) -> tuple[str, ...]:
    return folders_by_person(db).get(person_id, ())


def owners(db: Database) -> dict[str, list[Person]]:
    """Quem cuida de cada pasta: só pessoas ativas e que não são assistentes. Pasta sem ninguém fica de fora."""
    mine = folders_by_person(db)
    result: dict[str, list[Person]] = {}
    for p in list_people(db):
        if p.is_assistant:
            continue
        for f in mine.get(p.id, ()):
            result.setdefault(f, []).append(p)
    return {f: result[f] for f in FOLDERS if f in result}


def set_folders(db: Database, now: datetime, actor: Person, person_id: int, folders: list[str]) -> tuple[str, ...]:
    """Troca as pastas de uma pessoa (só administrador). Devolve as pastas que ficaram."""
    if not actor.is_admin:
        raise PermissionError("Só um administrador muda as pastas das pessoas.")
    if any(f not in FOLDERS for f in folders):
        raise ValidationError("Pasta inválida.")
    chosen = tuple(f for f in FOLDERS if f in folders)
    with db.connect() as conn:
        row = conn.execute("SELECT name, role FROM people WHERE id = ? AND active = 1", (person_id,)).fetchone()
        if row is None:
            raise ValidationError("Pessoa não encontrada.")
        if row["role"] == "assistente" and chosen:
            raise ValidationError("Assistente não tem pasta própria: mude o papel antes de escolher pastas.")
        before = tuple(f for f in FOLDERS if conn.execute(
            "SELECT 1 FROM person_folders WHERE person_id = ? AND folder = ?", (person_id, f)).fetchone())
        if before == chosen:
            return chosen
        conn.execute("DELETE FROM person_folders WHERE person_id = ?", (person_id,))
        conn.executemany("INSERT INTO person_folders(person_id, folder) VALUES (?, ?)", [(person_id, f) for f in chosen])
        log_event(conn, now, actor.id, "pastas_alteradas", f"pessoa:{person_id}",
                  f"{row['name']}: {', '.join(chosen) or 'nenhuma'}")
    return chosen
