# Registre des tests

Consigne chaque test écrit. Quand la séparation s'applique, seul le rôle test-writer modifie ce fichier.

Aides partagées (pas des tests) : `tests/support.py` (`ScriptedModel`, `Console`, `make_config`, `run_repl`, `one_turn`), `tests/conftest.py` (`workdir`, `sigint`).

## specs/001-v0-boucle-agent.md — v0 : la boucle d'agent

| ID | Test (fichier › nom) | Point d'entrée | Couvre | Type | Ajouté | Statut |
|---|---|---|---|---|---|---|
| T-0001 | tests/test_agent_loop.py › test_agent_chains_read_write_shell_in_one_turn_with_paths_relative_to_workdir | `Session.run_turn` | CA-5, CA-4 (partie testable, ADR-0002) — l'agent n'enchaîne pas les actions ; écrit hors du dossier de travail | integration | 2026-11-15 | active |
| T-0002 | tests/test_agent_loop.py › test_history_is_kept_across_turns_of_a_session | `Session.run_turn` | CA-2 — historique perdu entre deux tours | integration | 2026-11-15 | active |
| T-0003 | tests/test_agent_loop.py › test_budget_reached_blocks_model_calls_until_granted_an_identical_slice | `Session.run_turn` / `resume_turn` | CA-17 — appel facturé au-delà du budget ; mauvaise tranche accordée | integration | 2026-11-15 | active |
| T-0004 | tests/test_tools.py › test_reading_a_missing_file_returns_the_error_to_the_model | `Session.run_turn` | CA-6 — erreur de lecture qui arrête la session | integration | 2026-11-15 | active |
| T-0005 | tests/test_tools.py › test_reading_a_binary_file_is_refused_explicitly | `Session.run_turn` | CA-7 — contenu binaire envoyé au modèle | integration | 2026-11-15 | active |
| T-0006 | tests/test_tools.py › test_long_file_and_long_command_output_are_truncated_with_explicit_mention | `Session.run_turn` | CA-8 — troncature silencieuse ou absente (lecture et commande) | integration | 2026-11-15 | active |
| T-0007 | tests/test_tools.py › test_write_creates_missing_folders_and_overwrites_existing_files | `Session.run_turn` | CA-9 — écriture qui échoue sur dossier absent ou fichier existant | integration | 2026-11-15 | active |
| T-0008 | tests/test_tools.py › test_failing_command_returns_exit_code_and_output_and_the_turn_continues | `Session.run_turn` | CA-10 — code de sortie / stderr perdus | integration | 2026-11-15 | active |
| T-0009 | tests/test_tools.py › test_command_exceeding_the_timeout_is_killed_and_partial_output_is_returned | `Session.run_turn` | CA-11 — commande sans fin qui bloque la session ; sortie partielle perdue | integration | 2026-11-15 | active |
| T-0010 | tests/test_tools.py › test_unknown_tool_and_invalid_arguments_are_returned_as_errors | `Session.run_turn` | spec §6, ADR-0002 §2 — appel d'outil sans résultat, historique corrompu | integration | 2026-11-15 | active |
| T-0011 | tests/test_repl.py › test_startup_shows_workdir_active_model_and_limits_then_a_prompt | `cli.repl.run` | CA-1 — l'utilisateur ignore où et avec quoi l'agent agit | e2e | 2026-11-15 | active |
| T-0012 | tests/test_repl.py › test_quit_command_and_ctrl_d_end_the_session_showing_total_cost | `cli.repl.run` | CA-3 — sortie impossible ou sans coût total (paramétré `/quit`, Ctrl+D) | e2e | 2026-11-15 | active |
| T-0013 | tests/test_repl.py › test_events_show_as_titles_by_default_and_in_full_after_toggling_detail | `cli.repl.run` | CA-12, CA-13 — mode titre qui déverse tout ; bascule `/detail` inopérante | e2e | 2026-11-15 | active |
| T-0039 | tests/test_repl.py › test_model_reply_is_shown_in_full_in_title_mode_even_when_long_and_multiline | `cli.repl.run` | CA-12 (amendé) — réponse du modèle tronquée en mode titre | e2e | 2026-11-15 | active |
| T-0014 | tests/test_repl.py › test_cumulative_cost_is_shown_after_each_turn_and_at_exit | `cli.repl.run` | CA-14 — coût non cumulé ou invisible | e2e | 2026-11-15 | active |
| T-0015 | tests/test_repl.py › test_unknown_cost_is_shown_as_not_estimated_and_does_not_trigger_the_budget | `cli.repl.run` | spec §6, ADR-0004 — coût inconnu affiché 0 ou consommant le budget | e2e | 2026-11-15 | active |
| T-0016 | tests/test_repl.py › test_step_limit_stops_the_agent_names_the_limit_and_asks_to_continue | `cli.repl.run` | CA-15 — boucle sans fin ; arrêt sans dire pourquoi | e2e | 2026-11-15 | active |
| T-0017 | tests/test_repl.py › test_continue_yes_grants_an_identical_slice_no_returns_to_prompt_other_reasks | `cli.repl.run` | CA-16, spec §6 (réponse ni oui ni non) — tranche fausse ; « non » qui ferme la session | e2e | 2026-11-15 | active |
| T-0018 | tests/test_repl.py › test_ctrl_c_at_the_prompt_does_not_quit | `cli.repl.run` | CA-19 — Ctrl+C à l'invite qui perd la session | e2e | 2026-11-15 | active |
| T-0019 | tests/test_interruption.py › test_ctrl_c_during_a_long_command_kills_it_and_next_request_sees_the_interruption | `cli.repl.run` + vrai SIGINT | CA-18 — commande non tuée ; modèle non informé ; session perdue | e2e | 2026-11-15 | active |
| T-0020 | tests/test_interruption.py › test_ctrl_c_during_the_model_call_interrupts_the_turn_and_keeps_the_session | `cli.repl.run` + vrai SIGINT | spec §6, ADR-0005 §2 — Ctrl+C pendant l'appel modèle qui casse la session | e2e | 2026-11-15 | active |
| T-0021 | tests/test_providers.py › test_startup_with_missing_api_key_names_the_key_and_opens_no_session | `cli.repl.run` + vrai `LiteLLMClient` | CA-20 — session ouverte sans clé ; cause non nommée | contract | 2026-11-15 | active |
| T-0022 | tests/test_providers.py › test_startup_with_unreachable_openai_compatible_server_names_it_and_opens_no_session | `cli.repl.run` + vrai `LiteLLMClient` (port fermé) | CA-21 — session ouverte sur serveur mort ; serveur non nommé | contract | 2026-11-15 | active |
| T-0023 | tests/test_providers.py › test_provider_unreachable_mid_session_shows_message_keeps_conversation_and_retries | `cli.repl.run` | CA-22 — conversation perdue ou session fermée sur erreur fournisseur | e2e | 2026-11-15 | active |
| T-0024 | tests/test_providers.py › test_launch_option_overrides_the_configured_model | `cli.repl.run(model_override=…)` | CA-23 — mauvais modèle (facturation) (paramétré avec/sans option) | e2e | 2026-11-15 | active |
| T-0025 | tests/test_providers.py › test_model_command_switches_the_active_model_and_keeps_history | `cli.repl.run` | CA-24 (succès) — `/model` sans effet ou historique perdu | e2e | 2026-11-15 | active |
| T-0026 | tests/test_providers.py › test_failed_model_switch_shows_a_message_and_keeps_the_previous_model | `cli.repl.run` | CA-24 (échec) — modèle actif perdu sur un changement raté | e2e | 2026-11-15 | active |

## Revue : couverture complémentaire (LiteLLMClient réel, config, résilience du tour)

| ID | Test (fichier › nom) | Point d'entrée | Couvre | Type | Ajouté | Statut |
|---|---|---|---|---|---|---|
| T-0027 | tests/test_litellm_client.py › test_profile_with_api_base_and_no_key_completes_and_sends_a_well_formed_request | `LiteLLMClient.complete` + faux serveur HTTP local | ADR-0003 §2, §4 — profil `api_base` sans clé en échec (« Missing credentials ») ; requête mal construite (modèle, messages, outils, max_tokens) | contract | 2026-11-15 | active |
| T-0028 | tests/test_litellm_client.py › test_tool_calls_in_the_response_are_translated_to_openai_chat_format | `LiteLLMClient.complete` | ADR-0003 §1, §6 — appels d'outils mal traduits | contract | 2026-11-15 | active |
| T-0029 | tests/test_litellm_client.py › test_cost_is_computed_from_declared_prices_and_none_when_prices_are_absent | `LiteLLMClient.complete` | ADR-0004 §1-2 — coût faux ou 0 trompeur (prix déclarés / absents, nom de modèle connu) | contract | 2026-11-15 | active |
| T-0030 | tests/test_litellm_client.py › test_zero_declared_prices_give_a_known_zero_cost | `LiteLLMClient.complete` | ADR-0004 §2 — prix 0 confondu avec prix absent | contract | 2026-11-15 | active |
| T-0031 | tests/test_litellm_client.py › test_http_errors_are_translated_to_provider_error_with_the_right_kind | `LiteLLMClient.complete` | ADR-0003 §5 — erreur auth / contexte trop long / autre non typée ou fuite d'exception LiteLLM (paramétré) | contract | 2026-11-15 | active |
| T-0032 | tests/test_litellm_client.py › test_unreachable_server_is_translated_to_provider_error_unreachable | `LiteLLMClient.complete` (port fermé) | ADR-0003 §5 — serveur injoignable en cours d'appel non classé `unreachable` | contract | 2026-11-15 | active |
| T-0033 | tests/test_config.py › test_invalid_profile_numbers_are_refused_naming_the_key | `load_config` | ADR-0007 — prix négatif/chaîne/booléen, `max_output_tokens` non entier acceptés (paramétré) | unit | 2026-11-15 | active |
| T-0034 | tests/test_config.py › test_zero_prices_are_accepted | `load_config` | ADR-0004 §2 — prix 0 refusé à tort | unit | 2026-11-15 | active |
| T-0035 | tests/test_resilience.py › test_provider_failure_after_a_successful_tool_call_keeps_session_usable_and_history_valid | `cli.repl.run` | ADR-0001 §7, spec §6 — historique invalide / session perdue après échec en milieu de tour | e2e | 2026-11-15 | active |
| T-0036 | tests/test_resilience.py › test_unexpected_client_exception_does_not_crash_the_repl | `cli.repl.run` | spec §6 — exception inattendue du client qui tue le REPL | e2e | 2026-11-15 | active |
| T-0037 | tests/test_resilience.py › test_cut_off_message_with_tool_calls_runs_nothing_and_informs_the_model | `Session.run_turn` | ADR-0002 §4 — appel tronqué exécuté ; modèle non informé | integration | 2026-11-15 | active |
| T-0038 | tests/test_resilience.py › test_external_timeout_around_a_turn_is_not_swallowed_silently | `Session.run_turn` dans `asyncio.timeout` | ADR-0005 §2 (amendé) — annulation externe avalée par le tour | integration | 2026-11-15 | active |
