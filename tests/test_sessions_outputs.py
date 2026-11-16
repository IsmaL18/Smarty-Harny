"""Sessions durables, tranche 3 (1/3) : secret masqué et sorties enregistrées conservées.

Spec 003 CA-S4 et CA-S19 ; ADR-0012 §2 (secrets), §5 ; ADR-0011 (sorties longues).
Seam : `cli.main.main` avec un modèle simulé, les vrais outils et la vraie
configuration TOML ; on lit les fichiers visibles sous `.harness/` du dossier de travail.
"""

from support import ScriptedModel, call, journals, launch, saved_path_in, say, tools

# Sortie de plus de 1000 caractères : elle est coupée pour le modèle et enregistrée en entier.
LONG_COMMAND = 'for i in $(seq 1 3000); do echo "sortie $i"; done'
SMALL_OUTPUTS = "[tools]\nmax_output_chars = 1000\n"


def _harness_files(workdir):
    root = workdir / ".harness"
    return [p for p in root.rglob("*") if p.is_file()]


def test_api_key_never_appears_in_the_journal_nor_in_saved_outputs(
    workdir, monkeypatch, capsys
):
    """CA-S4 : la valeur de la clé lue de l'environnement, même affichée par une
    commande `env` du modèle, n'est écrite ni dans le journal ni dans les sorties
    enregistrées ; elle y est remplacée par `[REDACTED]`."""
    secret = "sk-test-0123456789-secret-value"
    monkeypatch.setenv("TEST_HARNESS_KEY", secret)
    show_env = call("shell", command=f"env | grep TEST_HARNESS_KEY; {LONG_COMMAND}")

    result = launch(
        [], ["montre l'environnement", "/quit"],
        {"scripted": ScriptedModel([tools(show_env), say("vu")])},
        workdir, monkeypatch, capsys,
        extra_toml=SMALL_OUTPUTS, profile_extra='api_key_env = "TEST_HARNESS_KEY"\n',
    )  # fmt: skip

    assert result.code == 0
    (journal,) = journals(workdir)
    for path in _harness_files(workdir):
        assert secret.encode() not in path.read_bytes(), f"clé en clair dans {path}"
    assert "[REDACTED]" in journal.read_text()
    saved = [p for p in _harness_files(workdir) if "outputs" in p.parts]
    assert saved, "la sortie longue devait être enregistrée"
    assert any("[REDACTED]" in p.read_text() for p in saved)


def test_saved_output_outlives_quit_and_resume_and_the_model_can_be_sent_to_it(
    workdir, monkeypatch, capsys
):
    """CA-S19 : un fichier de sortie enregistré avant la fermeture existe encore
    après `/quit` puis après la reprise, et le renvoi du modèle vers ce fichier
    fonctionne (il n'est plus supprimé à la sortie)."""
    run_long = call("shell", command=LONG_COMMAND)
    first = ScriptedModel([tools(run_long), say("fini")])
    launch(
        [], ["lance la commande longue", "/quit"], {"scripted": first},
        workdir, monkeypatch, capsys, extra_toml=SMALL_OUTPUTS,
    )  # fmt: skip
    saved = workdir / saved_path_in(first.tool_output(run_long))
    assert saved.is_file(), "sortie enregistrée supprimée à la fermeture"
    (journal,) = journals(workdir)

    reread = call("read_file", path=str(saved), offset=1500, limit=2)
    second = ScriptedModel([tools(reread), say("relu")])
    result = launch(
        ["--resume", journal.stem], ["relis le fichier de sortie", "/quit"],
        {"scripted": second}, workdir, monkeypatch, capsys, extra_toml=SMALL_OUTPUTS,
    )  # fmt: skip

    assert result.code == 0
    assert "sortie 1500" in second.tool_output(reread)
    assert saved.is_file(), "sortie enregistrée supprimée après la reprise"
