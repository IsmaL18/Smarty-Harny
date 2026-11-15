"""Modification partielle d'un fichier : contrat, lu avant de modifier, tolérance.

Spec 002 §4.1 à §4.3, CA-26 à CA-39 ; ADR-0010. Un refus ne laisse aucune trace
sur le fichier (spec §7). Chaque test joue un tour réel : le modèle simulé
demande l'action, le vrai outil s'exécute sur un vrai dossier, et on lit le
fichier sur le disque et la réponse reçue par le modèle. Les changements
« extérieurs » sont faits entre deux tours, comme le ferait l'utilisateur.

Les messages d'erreur ne sont vérifiés que par leur marqueur `error:` et par
l'information que la spec exige (nombre d'occurrences, rang du remplacement
fautif, conseil de lecture).
"""

import os
import re
import time

import pytest
from support import (
    ScriptedModel,
    call,
    collect,
    edit,
    ended_with,
    make_config,
    make_session,
    one_turn,
    refused,
    replace,
    say,
    tools,
)


def _rank(number: int) -> re.Pattern[str]:
    return re.compile(rf"(?<!\d){number}(?!\d)")


async def test_single_replacement_changes_only_that_text_and_confirms(workdir):
    """CA-26 : le texte exact est remplacé, le reste du fichier est identique
    octet pour octet (accents, fin sans saut de ligne), le modèle reçoit une confirmation."""
    original = "intro café\nvaleur = 1\nfin sans saut de ligne".encode()
    (workdir / "a.txt").write_bytes(original)
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace("valeur = 1", "valeur = 2"))

    model, events = await one_turn(workdir, tools(read), tools(change), say("fait"))

    assert ended_with(events) == "done"
    assert (workdir / "a.txt").read_bytes() == (
        "intro café\nvaleur = 2\nfin sans saut de ligne".encode()
    )
    assert not model.tool_output(change).startswith("error:")


async def test_several_replacements_in_one_action_are_all_applied_and_counted(workdir):
    """CA-27 : zones distinctes, tous appliqués (dont un texte sur plusieurs
    lignes), le résultat indique leur nombre."""
    (workdir / "a.txt").write_text("un\ndeux\ntrois\nquatre\n")
    read = call("read_file", path="a.txt")
    change = edit(
        "a.txt", replace("un", "UN"), replace("trois\nquatre", "TROIS\nQUATRE")
    )

    model, _ = await one_turn(workdir, tools(read), tools(change), say("fait"))

    assert (workdir / "a.txt").read_text() == "UN\ndeux\nTROIS\nQUATRE\n"
    assert not model.tool_output(change).startswith("error:")
    assert _rank(2).search(model.tool_output(change))


async def test_text_not_found_leaves_the_file_intact_and_the_session_continues(
    workdir,
):
    """CA-28 : introuvable (ni exact ni tolérant) → erreur, fichier intact, le
    modèle peut se corriger au tour de boucle suivant."""
    (workdir / "a.txt").write_text("alpha\nbeta\n")
    read = call("read_file", path="a.txt")
    wrong = edit("a.txt", replace("gamma", "GAMMA"))
    fixed = edit("a.txt", replace("beta", "BETA"))

    model, events = await one_turn(
        workdir, tools(read), tools(wrong), tools(fixed), say("corrigé")
    )

    assert ended_with(events) == "done"
    assert refused(model.tool_output(wrong))
    assert (workdir / "a.txt").read_text() == "alpha\nBETA\n"


async def test_ambiguous_text_is_refused_with_the_occurrence_count(workdir):
    """CA-29 : texte présent trois fois → refus, fichier intact, le nombre
    d'occurrences est donné."""
    (workdir / "a.txt").write_text("x = 1\ny\nx = 1\nz\nx = 1\n")
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace("x = 1", "x = 2"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("vu"))

    output = model.tool_output(change)
    assert refused(output)
    assert _rank(3).search(output)
    assert (workdir / "a.txt").read_text() == "x = 1\ny\nx = 1\nz\nx = 1\n"


@pytest.mark.parametrize(
    ("replacements", "faulty_rank"),
    [
        ([("un", "UN"), ("absent", "X")], 2),
        ([("deux", "DEUX"), ("ligne", "X")], 2),  # « ligne » : trois occurrences
        ([("ligne un", "A"), ("ligne un", "B")], None),  # même texte deux fois
        ([("ligne un\nligne", "A"), ("un\nligne deux", "B")], None),  # chevauchement
    ],
    ids=["introuvable", "ambigu", "meme-texte", "chevauchement"],
)
async def test_one_failing_replacement_applies_none_and_names_the_faulty_one(
    workdir, replacements, faulty_rank
):
    """CA-30 : tout ou rien. Le premier remplacement, valide, n'est pas appliqué
    non plus ; le message nomme le remplacement fautif quand il est identifiable."""
    content = "ligne un\nligne deux\nligne trois\n"
    (workdir / "a.txt").write_text(content)
    read = call("read_file", path="a.txt")
    change = edit("a.txt", *(replace(old, new) for old, new in replacements))

    model, events = await one_turn(workdir, tools(read), tools(change), say("vu"))

    output = model.tool_output(change)
    assert ended_with(events) == "done"
    assert refused(output)
    assert (workdir / "a.txt").read_text() == content
    if faulty_rank is not None:
        assert _rank(faulty_rank).search(output)


@pytest.mark.parametrize(
    "case",
    ["texte-vide", "texte-identique", "fichier-absent", "fichier-binaire"],
)
async def test_unusable_requests_are_refused_and_nothing_is_changed_or_created(
    workdir, case
):
    """CA-31 : refus explicite, fichier intact, rien créé pour un fichier absent."""
    (workdir / "a.txt").write_text("contenu\n")
    (workdir / "b.bin").write_bytes(b"BIN\x00\x01contenu\xff")
    read_text = call("read_file", path="a.txt")
    read_binary = call("read_file", path="b.bin")
    change = {
        "texte-vide": edit("a.txt", replace("", "x")),
        "texte-identique": edit("a.txt", replace("contenu", "contenu")),
        "fichier-absent": edit("absent.txt", replace("a", "b")),
        "fichier-binaire": edit("b.bin", replace("contenu", "autre")),
    }[case]

    model, events = await one_turn(
        workdir, tools(read_text, read_binary), tools(change), say("vu")
    )

    assert ended_with(events) == "done"
    assert refused(model.tool_output(change))
    assert (workdir / "a.txt").read_text() == "contenu\n"
    assert (workdir / "b.bin").read_bytes() == b"BIN\x00\x01contenu\xff"
    assert not (workdir / "absent.txt").exists()


async def test_empty_file_and_missing_final_newline_are_preserved(workdir):
    """Spec §6 : un fichier vide reste vide après un refus ; un fichier sans
    saut de ligne final n'en gagne pas (couvert aussi par CA-26)."""
    (workdir / "vide.txt").write_bytes(b"")
    read = call("read_file", path="vide.txt")
    change = edit("vide.txt", replace("x", "y"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("vu"))

    assert refused(model.tool_output(change))
    assert (workdir / "vide.txt").read_bytes() == b""


async def test_a_file_never_read_is_refused_until_it_is_read(workdir):
    """CA-32 : refus sans effet, le message dit de lire d'abord ; après la
    lecture, la même modification passe."""
    (workdir / "a.txt").write_text("avant\n")
    change = edit("a.txt", replace("avant", "après"))
    read = call("read_file", path="a.txt")
    again = edit("a.txt", replace("avant", "après"))

    model, _ = await one_turn(
        workdir, tools(change), tools(read), tools(again), say("fait")
    )

    output = model.tool_output(change)
    assert refused(output)
    assert "read" in output.lower()
    assert not model.tool_output(again).startswith("error:")
    assert (workdir / "a.txt").read_text() == "après\n"


@pytest.mark.parametrize("how", ["lecture-tronquee", "lecture-par-plage"])
async def test_any_read_is_enough_even_truncated_or_by_range(workdir, how):
    """CA-33 et spec §6 : une lecture tronquée ou par plage suffit, y compris
    pour modifier une zone qui n'a pas été montrée."""
    lines = [f"ligne {i:03d}" for i in range(1, 301)]
    (workdir / "grand.txt").write_text("\n".join(lines) + "\n")
    if how == "lecture-tronquee":
        read = call("read_file", path="grand.txt")
        config = make_config(max_read=600)
    else:
        read = call("read_file", path="grand.txt", offset=1, limit=2)
        config = make_config()
    change = edit("grand.txt", replace("ligne 150\n", "ligne 150 modifiée\n"))

    model, _ = await one_turn(
        workdir, tools(read), tools(change), say("fait"), config=config
    )

    assert not model.tool_output(change).startswith("error:")
    assert "ligne 150 modifiée" in (workdir / "grand.txt").read_text()


async def test_a_file_written_or_edited_by_the_agent_can_be_edited_without_rereading(
    workdir,
):
    """CA-34 : écrit en entier, puis modifié deux fois de suite, sans relecture."""
    write = call("write_file", path="n.txt", content="un\ndeux\ntrois\n")
    first = edit("n.txt", replace("un", "UN"))
    second = edit("n.txt", replace("trois", "TROIS"))

    model, _ = await one_turn(
        workdir, tools(write), tools(first), tools(second), say("fait")
    )

    assert not model.tool_output(first).startswith("error:")
    assert not model.tool_output(second).startswith("error:")
    assert (workdir / "n.txt").read_text() == "UN\ndeux\nTROIS\n"


async def test_external_change_after_reading_is_refused_until_reread(workdir):
    """CA-35 : fichier lu, puis changé par l'utilisateur (hors agent) → refus,
    le changement extérieur est conservé, le message demande de relire ; après
    relecture, la modification passe."""
    target = workdir / "a.txt"
    target.write_text("clé = 1\nautre = 1\n")
    model = ScriptedModel()
    session = make_session(make_config(), workdir, model)

    model.script = [tools(call("read_file", path="a.txt")), say("lu")]
    await collect(session.run_turn("lis"))
    target.write_text("clé = 1\nautre = 99\najout extérieur\n")  # changement extérieur

    stale = edit("a.txt", replace("clé = 1", "clé = 2"))
    reread = call("read_file", path="a.txt")
    retry = edit("a.txt", replace("clé = 1", "clé = 2"))
    model.script = [tools(stale), tools(reread), tools(retry), say("fait")]
    await collect(session.run_turn("modifie"))

    refusal = model.tool_output(stale)
    assert refused(refusal)
    assert "read" in refusal.lower()
    assert not model.tool_output(retry).startswith("error:")
    assert target.read_text() == "clé = 2\nautre = 99\najout extérieur\n"


async def test_touching_a_file_without_changing_it_does_not_cause_a_refusal(workdir):
    """ADR-0010 §4 : seul le contenu compte, jamais la date de modification."""
    target = workdir / "a.txt"
    target.write_text("clé = 1\n")
    model = ScriptedModel()
    session = make_session(make_config(), workdir, model)
    model.script = [tools(call("read_file", path="a.txt")), say("lu")]
    await collect(session.run_turn("lis"))
    later = time.time() + 120
    os.utime(target, (later, later))

    change = edit("a.txt", replace("clé = 1", "clé = 2"))
    model.script = [tools(change), say("fait")]
    await collect(session.run_turn("modifie"))

    assert target.read_text() == "clé = 2\n"


async def test_change_made_by_the_agents_own_shell_command_does_not_block_editing(
    workdir,
):
    """CA-36 : lu, puis changé par une commande shell de l'agent : la
    modification passe si le texte correspond au contenu réel du fichier."""
    (workdir / "a.txt").write_text("état = ancien\n")
    read = call("read_file", path="a.txt")
    shell = call("shell", command="printf 'état = par-le-shell\\n' > a.txt")
    change = edit("a.txt", replace("par-le-shell", "final"))

    model, _ = await one_turn(
        workdir, tools(read), tools(shell), tools(change), say("fait")
    )

    assert not model.tool_output(change).startswith("error:")
    assert (workdir / "a.txt").read_text() == "état = final\n"


async def test_external_change_made_before_a_shell_command_is_still_detected(workdir):
    """ADR-0010 §5 (CA-36 sans affaiblir CA-35) : un changement extérieur
    antérieur à la commande n'est pas « absorbé » par elle."""
    target = workdir / "a.txt"
    target.write_text("clé = 1\n")
    model = ScriptedModel()
    session = make_session(make_config(), workdir, model)
    model.script = [tools(call("read_file", path="a.txt")), say("lu")]
    await collect(session.run_turn("lis"))
    target.write_text("clé = 1\nmodifié par l'utilisateur\n")

    shell = call("shell", command="true")
    change = edit("a.txt", replace("clé = 1", "clé = 2"))
    model.script = [tools(shell), tools(change), say("vu")]
    await collect(session.run_turn("modifie"))

    assert refused(model.tool_output(change))
    assert target.read_text() == "clé = 1\nmodifié par l'utilisateur\n"


async def test_file_deleted_by_a_command_gives_a_missing_file_error_not_a_creation(
    workdir,
):
    """Spec §6 : supprimé par une commande après sa lecture, puis modification
    demandée : erreur « fichier absent », rien n'est recréé."""
    (workdir / "a.txt").write_text("contenu\n")
    read = call("read_file", path="a.txt")
    shell = call("shell", command="rm a.txt")
    change = edit("a.txt", replace("contenu", "autre"))

    model, _ = await one_turn(
        workdir, tools(read), tools(shell), tools(change), say("vu")
    )

    assert refused(model.tool_output(change))
    assert not (workdir / "a.txt").exists()


# --- Tolérance -----------------------------------------------------------

_TOLERANCE_CASES = {
    "fins-de-ligne": (
        b"a = 1\r\nb = 2\r\nc = 3\r\n",
        "a = 1\nb = 2\n",
        "a = 10\nb = 20\n",
        b"a = 10\r\nb = 20\r\nc = 3\r\n",
    ),
    "espaces-de-fin": (
        b"a = 1   \nb = 2\t\nc = 3\n",
        "a = 1\nb = 2\n",
        "a = 10\nb = 20\n",
        b"a = 10\nb = 20\nc = 3\n",
    ),
    "guillemets-et-tirets": (
        "dit \u201cbonjour\u201d \u2014 puis l\u2019adieu\n".encode(),
        'dit "bonjour" - puis l\'adieu',
        "dit salut",
        b"dit salut\n",
    ),
    "indentation": (
        b"def f():\n        return 1\n",
        "def f():\n    return 1",
        "def f():\n    return 2",
        b"def f():\n        return 2\n",
    ),
}


@pytest.mark.parametrize("case", list(_TOLERANCE_CASES))
async def test_text_differing_only_by_form_is_matched_silently(workdir, case):
    """CA-37 : fins de ligne, espaces de fin, guillemets/tirets typographiques
    ou indentation : la modification est appliquée, sans mention de tolérance."""
    original, old_text, new_text, expected = _TOLERANCE_CASES[case]
    (workdir / "a.txt").write_bytes(original)
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace(old_text, new_text))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("fait"))

    output = model.tool_output(change)
    assert not output.startswith("error:")
    assert not re.search(r"toler|fuzzy|approx|normali", output, re.IGNORECASE)
    assert (workdir / "a.txt").read_bytes() == expected


@pytest.mark.parametrize("matching", ["exact", "tolerant"])
async def test_crlf_file_stays_entirely_crlf_after_an_edit(workdir, matching):
    """CA-38 : après un appariement exact comme tolérant, un nouveau texte sur
    plusieurs lignes ne mélange pas les fins de ligne."""
    (workdir / "a.txt").write_bytes(b"debut\r\nmilieu\r\nfin\r\n")
    read = call("read_file", path="a.txt")
    old_text = "milieu" if matching == "exact" else "debut\nmilieu"
    change = edit("a.txt", replace(old_text, "un\ndeux\ntrois"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("fait"))

    result = (workdir / "a.txt").read_bytes()
    assert not model.tool_output(change).startswith("error:")
    assert b"deux" in result
    assert b"\n" not in result.replace(b"\r\n", b"")


async def test_a_unique_exact_match_wins_over_tolerant_candidates(workdir):
    """CA-39 : une correspondance exacte unique l'emporte, même si l'appariement
    tolérant en trouverait deux."""
    (workdir / "a.txt").write_bytes(b"a  \nb\nmilieu\na\nb\n")
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace("a\nb", "A\nB"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("fait"))

    assert not model.tool_output(change).startswith("error:")
    assert (workdir / "a.txt").read_bytes() == b"a  \nb\nmilieu\nA\nB\n"


async def test_ambiguous_tolerant_match_is_refused_and_the_file_is_intact(workdir):
    """CA-39 : plusieurs correspondances tolérantes, aucune exacte → refus d'ambiguïté."""
    content = b"a  \nb\nmilieu\na\t\nb\n"
    (workdir / "a.txt").write_bytes(content)
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace("a\nb", "A\nB"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("vu"))

    output = model.tool_output(change)
    assert refused(output)
    assert _rank(2).search(output)
    assert (workdir / "a.txt").read_bytes() == content


async def test_new_text_follows_the_files_indentation_after_a_tolerant_match(workdir):
    """ADR-0010 §10 : après un appariement tolérant dont l'indentation diffère,
    le nouveau texte est réindenté comme le fichier (tabulations ici)."""
    (workdir / "a.py").write_bytes(b"def f():\n\tif x:\n\t\treturn 1\n")
    read = call("read_file", path="a.py")
    change = edit(
        "a.py",
        replace(
            "    if x:\n        return 1", "    if x:\n        y = 2\n        return y"
        ),
    )

    await one_turn(workdir, tools(read), tools(change), say("fait"))

    assert (workdir / "a.py").read_bytes() == (
        b"def f():\n\tif x:\n\t\ty = 2\n\t\treturn y\n"
    )


async def test_multiline_tolerant_match_must_cover_whole_lines(workdir):
    """ADR-0010 §8 : un `old_text` sur plusieurs lignes qui ne s'apparie qu'en
    milieu de ligne est refusé (« introuvable ») et le fichier reste intact."""
    content = b"ab = 2\n  c = 3\n"
    (workdir / "a.txt").write_bytes(content)
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace("b = 2\nc = 3", "X"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("vu"))

    output = model.tool_output(change)
    assert refused(output)
    assert "not found" in output
    assert (workdir / "a.txt").read_bytes() == content


async def test_multiline_match_on_whole_lines_tolerates_a_different_indentation(
    workdir,
):
    """ADR-0010 §8 : un `old_text` sur plusieurs lignes entières, indenté
    autrement que le fichier, reste apparié."""
    (workdir / "a.txt").write_bytes(b"ab = 2\n  c = 3\nfin\n")
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace("ab = 2\nc = 3", "X"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("fait"))

    assert not model.tool_output(change).startswith("error:")
    assert b"X" in (workdir / "a.txt").read_bytes()
    assert b"c = 3" not in (workdir / "a.txt").read_bytes()


async def test_single_line_tolerant_match_in_mid_line_is_still_accepted(workdir):
    """ADR-0010 §8 : un `old_text` d'une seule ligne, apparié en milieu de
    ligne grâce à la normalisation (guillemets typographiques), reste toléré."""
    (workdir / "a.txt").write_bytes(b'ab = "x"\n')
    read = call("read_file", path="a.txt")
    change = edit("a.txt", replace("b = \u201cx\u201d", "b = 1"))

    model, _ = await one_turn(workdir, tools(read), tools(change), say("fait"))

    assert not model.tool_output(change).startswith("error:")
    assert (workdir / "a.txt").read_bytes() == b"ab = 1\n"


# --- Dossier réservé -----------------------------------------------------


@pytest.mark.parametrize("target", ["relatif", "absolu"])
async def test_write_and_edit_refuse_the_reserved_harness_folder(workdir, target):
    """ADR-0011 §13 : ni `write_file` ni `edit_file` ne touchent à `.harness/`."""
    (workdir / ".harness").mkdir()
    (workdir / ".harness" / "note.txt").write_text("existant\n")
    prefix = f"{workdir}/" if target == "absolu" else ""
    note = f"{prefix}.harness/note.txt"
    read = call("read_file", path=note)
    overwrite = call("write_file", path=note, content="écrasé\n")
    create = call("write_file", path=f"{prefix}.harness/nouveau.txt", content="x\n")
    change = edit(note, replace("existant", "modifié"))

    model, events = await one_turn(
        workdir, tools(read), tools(overwrite, create, change), say("vu")
    )

    assert ended_with(events) == "done"
    for attempt in (overwrite, create, change):
        assert refused(model.tool_output(attempt))
    assert (workdir / ".harness" / "note.txt").read_text() == "existant\n"
    assert not (workdir / ".harness" / "nouveau.txt").exists()
