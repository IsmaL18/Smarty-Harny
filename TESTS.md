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
| T-0006 | tests/test_tools.py › test_long_file_and_long_command_output_are_truncated_with_explicit_mention | `Session.run_turn` | CA-8 — troncature silencieuse ou absente (lecture et commande) | integration | 2026-11-15 | removed 2026-11-15 : CA-8 remplacé par la spec 002 (coupe au milieu) ; repris par T-0071 à T-0073 et T-0076 |
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

## specs/002-conception-des-outils.md — Concevoir de bons outils (CA-26 à CA-52)

Aides ajoutées dans `tests/support.py` (pas des tests) : étape dynamique du modèle simulé, `edit`, `replace`, `refused`, `config_from_toml`, `saved_path_in`.

| ID | Test (fichier › nom) | Point d'entrée | Couvre | Type | Ajouté | Statut |
|---|---|---|---|---|---|---|
| T-0040 | tests/test_edit_file.py › test_single_replacement_changes_only_that_text_and_confirms | `Session.run_turn` (edit_file) | CA-26 — fichier altéré hors de la zone modifiée (octets, fin sans saut de ligne) | integration | 2026-11-15 | active |
| T-0041 | tests/test_edit_file.py › test_several_replacements_in_one_action_are_all_applied_and_counted | `Session.run_turn` | CA-27 — remplacements perdus ou non comptés | integration | 2026-11-15 | active |
| T-0042 | tests/test_edit_file.py › test_text_not_found_leaves_the_file_intact_and_the_session_continues | `Session.run_turn` | CA-28 — fichier abîmé ou session cassée sur texte introuvable | integration | 2026-11-15 | active |
| T-0043 | tests/test_edit_file.py › test_ambiguous_text_is_refused_with_the_occurrence_count | `Session.run_turn` | CA-29 — remplacement au mauvais endroit sur texte ambigu | integration | 2026-11-15 | active |
| T-0044 | tests/test_edit_file.py › test_one_failing_replacement_applies_none_and_names_the_faulty_one | `Session.run_turn` | CA-30 — application partielle (introuvable, ambigu, même texte, chevauchement) (paramétré ×4) | integration | 2026-11-15 | active |
| T-0045 | tests/test_edit_file.py › test_unusable_requests_are_refused_and_nothing_is_changed_or_created | `Session.run_turn` | CA-31 — texte vide, identique, fichier absent (création), binaire (paramétré ×4) | integration | 2026-11-15 | active |
| T-0046 | tests/test_edit_file.py › test_empty_file_and_missing_final_newline_are_preserved | `Session.run_turn` | spec §6 — fichier vide altéré par un refus | integration | 2026-11-15 | active |
| T-0047 | tests/test_edit_file.py › test_a_file_never_read_is_refused_until_it_is_read | `Session.run_turn` | CA-32 — modification d'un fichier jamais lu ; message sans conseil | integration | 2026-11-15 | active |
| T-0048 | tests/test_edit_file.py › test_any_read_is_enough_even_truncated_or_by_range | `Session.run_turn` | CA-33, spec §6 — lecture tronquée/par plage qui n'autorise pas la modification (paramétré ×2) | integration | 2026-11-15 | active |
| T-0049 | tests/test_edit_file.py › test_a_file_written_or_edited_by_the_agent_can_be_edited_without_rereading | `Session.run_turn` | CA-34 — relecture exigée à tort après écriture ou modification propre | integration | 2026-11-15 | active |
| T-0050 | tests/test_edit_file.py › test_external_change_after_reading_is_refused_until_reread | `Session.run_turn` ×2 tours | CA-35 — écrasement d'un changement extérieur | integration | 2026-11-15 | active |
| T-0051 | tests/test_edit_file.py › test_touching_a_file_without_changing_it_does_not_cause_a_refusal | `Session.run_turn` ×2 tours | ADR-0010 §4 — faux refus sur simple `touch` (mtime) | integration | 2026-11-15 | active |
| T-0052 | tests/test_edit_file.py › test_change_made_by_the_agents_own_shell_command_does_not_block_editing | `Session.run_turn` | CA-36 — faux refus après un changement par le shell de l'agent | integration | 2026-11-15 | active |
| T-0053 | tests/test_edit_file.py › test_external_change_made_before_a_shell_command_is_still_detected | `Session.run_turn` ×2 tours | ADR-0010 §5 — changement extérieur masqué par un appel shell | integration | 2026-11-15 | active |
| T-0054 | tests/test_edit_file.py › test_file_deleted_by_a_command_gives_a_missing_file_error_not_a_creation | `Session.run_turn` | spec §6, ADR-0010 §6 — fichier supprimé recréé par une modification | integration | 2026-11-15 | active |
| T-0055 | tests/test_edit_file.py › test_text_differing_only_by_form_is_matched_silently | `Session.run_turn` | CA-37 — tolérance absente ou bavarde (fins de ligne, espaces de fin, guillemets/tirets, indentation) (paramétré ×4) | integration | 2026-11-15 | active |
| T-0056 | tests/test_edit_file.py › test_crlf_file_stays_entirely_crlf_after_an_edit | `Session.run_turn` | CA-38 — fichier CRLF mélangé en LF/CRLF (exact et tolérant) (paramétré ×2) | integration | 2026-11-15 | active |
| T-0057 | tests/test_edit_file.py › test_a_unique_exact_match_wins_over_tolerant_candidates | `Session.run_turn` | CA-39 — exact unique écarté par des candidats tolérants | integration | 2026-11-15 | active |
| T-0058 | tests/test_edit_file.py › test_ambiguous_tolerant_match_is_refused_and_the_file_is_intact | `Session.run_turn` | CA-39 — modification devinée sur correspondance tolérante ambiguë | integration | 2026-11-15 | active |
| T-0059 | tests/test_edit_file.py › test_new_text_follows_the_files_indentation_after_a_tolerant_match | `Session.run_turn` | ADR-0010 §10 — nouveau texte mal indenté après appariement tolérant | integration | 2026-11-15 | active |
| T-0060 | tests/test_edit_file.py › test_write_and_edit_refuse_the_reserved_harness_folder | `Session.run_turn` | ADR-0011 §13 — écriture/modification sous `.harness/` (relatif et absolu) (paramétré ×2) | integration | 2026-11-15 | active |
| T-0061 | tests/test_tool_arguments.py › test_wrong_but_unambiguous_argument_shapes_work_as_the_right_shape | `Session.run_turn` | CA-46 — erreurs de forme (nombre en texte, remplacement seul, liste en texte JSON) qui font échouer un appel juste (paramétré ×3) | integration | 2026-11-15 | active |
| T-0062 | tests/test_tool_arguments.py › test_unusable_arguments_fail_naming_the_argument_and_the_session_continues | `Session.run_turn` | CA-47 — argument manquant, inconnu, JSON invalide sans nom de l'argument (paramétré ×3) | integration | 2026-11-15 | active |
| T-0063 | tests/test_tool_arguments.py › test_a_number_that_is_not_convertible_says_the_expected_form | `Session.run_turn` | CA-47, ADR-0009 §7 — nombre non convertible sans forme attendue | integration | 2026-11-15 | active |
| T-0064 | tests/test_tool_arguments.py › test_default_toolset_gives_the_model_the_four_tools | `Session.run_turn` (outils vus) | CA-48 — outil manquant dans l'ensemble par défaut | integration | 2026-11-15 | active |
| T-0065 | tests/test_tool_arguments.py › test_read_only_toolset_hides_the_other_tools_and_refuses_calls_to_them | `Session.run_turn` + config TOML | CA-49 — outil d'écriture/shell visible ou exécuté en lecture seule | integration | 2026-11-15 | active |
| T-0066 | tests/test_tool_arguments.py › test_unknown_toolset_is_refused_naming_it_and_listing_the_existing_ones | `load_config` | CA-50 — ensemble inconnu accepté ; message sans nom ni liste | unit | 2026-11-15 | active |
| T-0067 | tests/test_tool_arguments.py › test_known_toolsets_are_accepted | `load_config` | CA-50 — ensembles valides refusés à tort | unit | 2026-11-15 | active |
| T-0068 | tests/test_tool_arguments.py › test_launch_shows_the_active_toolset | `cli.repl.run` | CA-51 — ensemble actif non affiché au lancement (paramétré ×2) | e2e | 2026-11-15 | active |
| T-0069 | tests/test_long_outputs.py › test_range_read_returns_exactly_those_lines_and_the_total | `Session.run_turn` (read_file) | CA-40 — mauvaise plage ou total absent | integration | 2026-11-15 | active |
| T-0070 | tests/test_long_outputs.py › test_range_outside_the_file_is_an_error_giving_the_total_line_count | `Session.run_turn` | CA-40 — plage hors fichier sans erreur claire | integration | 2026-11-15 | active |
| T-0071 | tests/test_long_outputs.py › test_long_file_is_cut_in_the_middle_and_the_omitted_zone_is_readable_by_range | `Session.run_turn` | CA-41 — fin du fichier perdue ; zone omise illisible | integration | 2026-11-15 | active |
| T-0072 | tests/test_long_outputs.py › test_a_single_giant_line_is_cut_by_characters_with_a_header | `Session.run_turn` | ADR-0011 §3 — ligne géante non bornée | integration | 2026-11-15 | active |
| T-0073 | tests/test_long_outputs.py › test_long_failing_command_keeps_its_start_its_end_and_the_exit_code | `Session.run_turn` (shell) | CA-42 — message d'erreur final perdu par la coupe | integration | 2026-11-15 | active |
| T-0074 | tests/test_long_outputs.py › test_the_header_gives_a_file_in_the_workdir_holding_the_full_output | `Session.run_turn` | CA-43, ADR-0011 §10 — sortie complète introuvable ; `.harness` non ignoré par Git | integration | 2026-11-15 | active |
| T-0075 | tests/test_long_outputs.py › test_short_command_leaves_nothing_on_disk | `Session.run_turn` | ADR-0011 §6 — fichiers pour les commandes courtes | integration | 2026-11-15 | active |
| T-0076 | tests/test_long_outputs.py › test_command_timeout_with_long_output_keeps_timeout_info_and_cuts_the_middle | `Session.run_turn` | CA-45 — dépassement de délai non signalé avec une longue sortie | integration | 2026-11-15 | active |
| T-0077 | tests/test_long_outputs.py › test_saved_output_stops_at_the_disk_cap_while_the_tail_stays_the_real_end | `Session.run_turn` + config TOML | ADR-0011 §7 — disque rempli ; fin factice | integration | 2026-11-15 | active |
| T-0078 | tests/test_long_outputs.py › test_saved_outputs_are_deleted_when_the_session_ends | `cli.repl.run` | CA-44 — sorties enregistrées laissées après `/quit` ou Ctrl+D (paramétré ×2) | e2e | 2026-11-15 | removed 2026-11-16: spec 003 §4.7 remplace CA-44 (les sorties enregistrées ne sont plus supprimées à la sortie) ; la durée de vie liée à la session sera testée avec CA-S19 |
| T-0079 | tests/test_long_outputs.py › test_stale_session_folders_are_purged_at_launch_but_recent_ones_are_kept | `cli.repl.run` | ADR-0011 §12 — restes de crash conservés ; session concurrente supprimée | e2e | 2026-11-15 | active |
| T-0080 | tests/test_edit_display.py › test_successful_edit_shows_a_title_then_the_diff_in_detailed_mode | `cli.repl.run` | CA-52 — nombre de remplacements absent ; diff absent ou toujours affiché | e2e | 2026-11-15 | active |
| T-0081 | tests/test_edit_file.py › test_multiline_tolerant_match_must_cover_whole_lines | `Session.run_turn` (edit_file) | ADR-0010 §8 — remplacement en milieu de ligne sur plusieurs lignes ; fichier modifié à tort | integration | 2026-11-15 | active |
| T-0082 | tests/test_edit_file.py › test_multiline_match_on_whole_lines_tolerates_a_different_indentation | `Session.run_turn` (edit_file) | ADR-0010 §8 — lignes entières à indentation différente refusées à tort | integration | 2026-11-15 | active |
| T-0083 | tests/test_edit_file.py › test_single_line_tolerant_match_in_mid_line_is_still_accepted | `Session.run_turn` (edit_file) | ADR-0010 §8 — tolérance mono-ligne en milieu de ligne supprimée par la correction | integration | 2026-11-15 | active |

## specs/003-sessions-et-mode-headless.md — Sessions et mode headless (tranche 1 : journal minimal et reprise)

Aides ajoutées dans `tests/support.py` (pas des tests) : `launch` (lance `cli.main.main(argv, client_factory=...)` avec saisie et sortie simulées), `journals`, `read_journal`.

| ID | Test (fichier › nom) | Point d'entrée | Couvre | Type | Ajouté | Statut |
|---|---|---|---|---|---|---|
| T-0084 | tests/test_sessions.py › test_journal_records_header_request_reply_action_result_and_usage | `cli.main.main` | CA-S1 — journal absent ou incomplet (en-tête, demande, réponse, appel, résultat reçu, coût) | integration | 2026-11-16 | active |
| T-0085 | tests/test_sessions.py › test_resume_only_appends_to_the_journal | `cli.main.main --resume` | CA-S5 — historique du journal réécrit à la reprise | integration | 2026-11-16 | active |
| T-0086 | tests/test_sessions.py › test_resumed_session_remembers_the_file_it_created | `cli.main.main --resume` | CA-S7 — historique perdu à la reprise | integration | 2026-11-16 | active |
| T-0087 | tests/test_sessions.py › test_resumed_session_keeps_cumulative_cost_and_partly_spent_budget | `cli.main.main --resume` | CA-S8 — coût et budget remis à zéro à la reprise | integration | 2026-11-16 | active |
| T-0088 | tests/test_sessions.py › test_resume_restores_active_model_and_model_option_overrides_and_records_it | `cli.main.main --resume --model` | CA-S9 — modèle non restauré, option ignorée ou non enregistrée | integration | 2026-11-16 | active |

## specs/003-sessions-et-mode-headless.md — Sessions et mode headless (tranche 2 : reprise robuste, liste, verrou, arrêt brutal)

Aide ajoutée (pas un test) : `tests/child_session.py`, processus enfant qui appelle `cli.main.main` avec un modèle simulé (modes `sleep` : bloqué en plein tour ; `hold` : REPL ouvert) pour les tests SIGKILL et session occupée. Les journaux corrompus sont dérivés d'un vrai journal produit par `launch`.

| ID | Test (fichier › nom) | Point d'entrée | Couvre | Type | Ajouté | Statut |
|---|---|---|---|---|---|---|
| T-0089 | tests/test_sessions_resume.py › test_sigkill_in_mid_turn_keeps_everything_before_the_current_entry | vrai sous-processus tué + `--resume` | CA-S2 — entrées d'avant perdues par un arrêt brutal ; journal illisible ; session non reprenable | e2e | 2026-11-16 | active |
| T-0090 | tests/test_sessions_resume.py › test_repl_opened_and_closed_without_a_request_leaves_no_session | `cli.main.main`, `--sessions` | CA-S3 — session fantôme créée sans demande | integration | 2026-11-16 | active |
| T-0091 | tests/test_sessions_resume.py › test_sessions_list_shows_each_session_of_the_folder_most_recent_first | `--sessions` | CA-S6 — liste incomplète, mal ordonnée ou mêlant les autres dossiers | integration | 2026-11-16 | active |
| T-0092 | tests/test_sessions_resume.py › test_file_read_before_closing_stays_editable_unless_changed_on_disk | `--resume` + `edit_file` | CA-S10 — fichiers lus perdus à la reprise ; changement sur disque non détecté (paramétré ×2) | integration | 2026-11-16 | active |
| T-0093 | tests/test_sessions_resume.py › test_resume_replays_the_conversation_after_a_header_in_the_closing_display_mode | `--resume` (REPL) | CA-S11 — en-tête absent ou incomplet ; rejeu dans le mauvais mode d'affichage (paramétré ×2) | e2e | 2026-11-16 | active |
| T-0094 | tests/test_sessions_resume.py › test_resume_command_closes_the_current_session_and_opens_the_chosen_one | REPL `/resume <id>` | CA-S12 — sessions mélangées ; session fermée non reprenable ; pas de rejeu | e2e | 2026-11-16 | active |
| T-0095 | tests/test_sessions_resume.py › test_a_unique_id_prefix_resumes_and_an_ambiguous_one_names_the_candidates | `--resume <préfixe>` | CA-S13 — préfixe ambigu résolu au hasard ; préfixe unique refusé | integration | 2026-11-16 | active |
| T-0096 | tests/test_sessions_resume.py › test_unusable_sessions_are_refused_with_the_cause_and_nothing_changes | `--resume` | CA-S14 + spec §6 dossier déplacé — session ouverte malgré id inconnu, autre dossier, format inconnu ou en-tête illisible ; journal modifié (paramétré ×4) | integration | 2026-11-16 | active |
| T-0097 | tests/test_sessions_resume.py › test_truncated_last_line_is_skipped_with_a_warning_and_the_file_is_never_rewritten | `--resume` | CA-S15 — reprise refusée ou fichier réécrit après une ligne tronquée ; journal réparé non reprenable une seconde fois | integration | 2026-11-16 | active |
| T-0098 | tests/test_sessions_resume.py › test_invalid_line_in_the_middle_or_broken_link_is_refused_naming_the_line | `--resume` | CA-S16 — journal corrompu au milieu accepté ou ligne non nommée (paramétré ×2) | integration | 2026-11-16 | active |
| T-0099 | tests/test_sessions_resume.py › test_call_without_result_gets_an_error_result_appended_and_the_model_is_told | `--resume` | CA-S17 — historique avec appel sans résultat envoyé au modèle ; résultat non ajouté au journal | integration | 2026-11-16 | active |
| T-0100 | tests/test_sessions_resume.py › test_resume_with_an_unreachable_model_fails_like_launch_and_changes_nothing | `--resume` + `ModelClient.check` | CA-S18 — session ouverte malgré modèle injoignable ; journal modifié | integration | 2026-11-16 | active |
| T-0101 | tests/test_sessions_resume.py › test_session_open_in_another_process_cannot_be_resumed_and_nothing_is_written | vrai sous-processus + `--resume` (REPL et `--prompt`) | CA-S25 — deux auteurs sur un journal ; message sans la session occupée | e2e | 2026-11-16 | active |
| T-0102 | tests/test_sessions_resume.py › test_session_left_busy_by_a_killed_process_is_resumable_without_manual_step | vrai sous-processus tué + `--resume` | CA-S26 — verrou d'un processus mort bloquant la session ; verrou non libéré à la sortie | e2e | 2026-11-16 | active |
| T-0103 | tests/test_sessions_resume.py › test_empty_or_header_only_journal_is_not_listed_and_resume_is_refused | `--sessions`, `--resume` | Spec §6 — journal vide ou en-tête seul listé ou repris (paramétré ×2) | integration | 2026-11-16 | active |
| T-0104 | tests/test_sessions_resume.py › test_sessions_opened_back_to_back_get_distinct_ids | `cli.main.main` | Spec §6, ADR §1.4 — deux sessions rapprochées écrasant le même journal | integration | 2026-11-16 | active |

## specs/003-sessions-et-mode-headless.md — Sessions et mode headless (tranche 3 : secret masqué, sorties conservées, branches, suppression, purge)

Aides ajoutées (pas des tests) : `tests/support.py` › `launch(..., extra_toml=, profile_extra=)` (clés TOML supplémentaires : `[tools]`, `[sessions]`, `api_key_env`), `spawn_open_session`, `kill_process_group`, `wait_for` (sous-processus de session occupée). Hypothèses d'interface : `/branch` affiche la liste numérotée puis lit le numéro choisi sur l'entrée suivante ; `--delete` lit « oui » / « non » sur l'entrée standard ; le message de purge contient « purg » ou « supprim » et le nombre.

| ID | Test (fichier › nom) | Point d'entrée | Couvre | Type | Ajouté | Statut |
|---|---|---|---|---|---|---|
| T-0105 | tests/test_sessions_outputs.py › test_api_key_never_appears_in_the_journal_nor_in_saved_outputs | `cli.main.main` + outil `shell` (`env`) | CA-S4 — clé API en clair dans le journal ou les sorties enregistrées | integration | 2026-11-16 | active |
| T-0106 | tests/test_sessions_outputs.py › test_saved_output_outlives_quit_and_resume_and_the_model_can_be_sent_to_it | `cli.main.main`, `--resume`, `read_file` | CA-S19 — sortie enregistrée supprimée à la sortie ; renvoi du modèle cassé | integration | 2026-11-16 | active |
| T-0107 | tests/test_sessions_branches.py › test_branch_lists_the_requests_and_restarts_from_before_the_chosen_one | REPL `/branch` | CA-S20, CA-S21 — historique de la nouvelle branche contaminé ; ancienne branche modifiée | integration | 2026-11-16 | active |
| T-0108 | tests/test_sessions_branches.py › test_closing_and_resuming_after_a_branch_reopens_the_new_branch_with_the_total_cost | REPL `/branch` + `--resume` | CA-S23, CA-S24 — coût de la branche abandonnée perdu ; reprise sur l'ancienne branche | integration | 2026-11-16 | active |
| T-0109 | tests/test_sessions_branches.py › test_after_a_branch_change_the_user_is_warned_the_model_is_told_and_files_must_be_reread | REPL `/branch` + `edit_file` | CA-S22 — fichiers lus d'une autre branche modifiables sans relecture ; avertissement ou message au modèle absent | integration | 2026-11-16 | active |
| T-0110 | tests/test_sessions_branches.py › test_branch_on_the_first_request_restarts_from_an_empty_history | REPL `/branch` | Spec §6 — branche sur la première demande | integration | 2026-11-16 | active |
| T-0111 | tests/test_sessions_branches.py › test_branch_with_no_request_says_so_without_error_and_the_session_goes_on | REPL `/branch` | Spec §6 — liste vide : erreur ou blocage | integration | 2026-11-16 | active |
| T-0112 | tests/test_sessions_retention.py › test_delete_asks_confirmation_then_removes_journal_and_saved_outputs | `--delete`, `--sessions` | CA-S27 — suppression sans confirmation ; sorties orphelines ; session encore listée | integration | 2026-11-16 | active |
| T-0113 | tests/test_sessions_retention.py › test_delete_is_refused_on_a_session_open_in_another_process | vrai sous-processus + `--delete` | CA-S27 — suppression d'une session occupée | e2e | 2026-11-16 | active |
| T-0114 | tests/test_sessions_retention.py › test_launch_purges_sessions_idle_longer_than_retention_days_except_recent_or_busy | lancement + `[sessions] retention_days` | CA-S28 — purge manquée, trop large, session occupée supprimée, sorties orphelines, nombre non annoncé | e2e | 2026-11-16 | active |

## specs/003-sessions-et-mode-headless.md — Sessions et mode headless (tranche 4 : mode headless)

Aides ajoutées ou modifiées (pas des tests) : `tests/support.py` › `Launch.asked` (invites de saisie affichées), `launch(..., max_steps=)`, `headless` (run `-p` par `cli.main.main`, à utiliser avec `capfd` ; `SystemExit` d'argparse rendu comme code), `jsonl_lines` (chaque ligne de stdout est un objet JSON avec `type`), `values`, `has_amount` ; `tests/child_headless.py`, processus enfant qui appelle `cli.main.main` avec un modèle simulé (scénarios `answer` : action puis bruit imprimé sur stdout puis réponse finale ; `sleep` : commande longue qui écrit son pid). Hypothèses d'interface : noms de lignes (`run_started`, `tool_call`, `tool_result`, `assistant_message`, `result`), champs `type`, `resumed`, `schema` (= 1), `is_error` et statuts `ok|error|limit|interrupted` pris de l'ADR-0012 §7 ; les autres champs du flux (session, modèle, dossier, réponse, étapes, tokens, coût, raison) ne sont pas nommés par l'ADR : les tests vérifient la présence de la valeur, pas le nom du champ. `main` appelé plusieurs fois dans un même processus de test (il doit rendre stdout et les gestionnaires de signaux en sortant). L'interruption est une entrée `state` de `kind` `interrupted` (ADR-0012 §2).

| ID | Test (fichier › nom) | Point d'entrée | Couvre | Type | Ajouté | Statut |
|---|---|---|---|---|---|---|
| T-0115 | tests/test_headless_process.py › test_prompt_run_ends_with_code_0_without_reading_standard_input | vrai sous-processus `-p`, stdin ouvert jamais écrit | CA-S29 — run headless qui attend une saisie ou ne se termine pas ; demande non exécutée | e2e | 2026-11-16 | active |
| T-0116 | tests/test_headless_process.py › test_text_output_puts_only_the_final_answer_on_stdout_and_everything_else_on_stderr | vrai sous-processus `--resume -p` (texte) | CA-S30, ADR-0012 §7 (impressions parasites) — stdout pollué (titres, coût, id, avertissement, bruit de bibliothèque) ; informations humaines absentes de stderr | e2e | 2026-11-16 | active |
| T-0117 | tests/test_headless.py › test_jsonl_stream_is_one_valid_object_per_line_from_run_started_to_result | `cli.main.main -p --output-format jsonl` | CA-S31 + spec §6 (texte multiligne, guillemets, non ASCII) — ligne non JSON ou sans `type` ; première/dernière ligne incomplètes ; réponse altérée | integration | 2026-11-16 | active |
| T-0118 | tests/test_headless_process.py › test_jsonl_events_are_written_while_the_action_is_still_running | vrai sous-processus `-p --output-format jsonl` | CA-S32 — flux JSONL émis en bloc à la fin (tampon non vidé) | e2e | 2026-11-16 | active |
| T-0119 | tests/test_headless.py › test_headless_run_creates_a_session_that_a_second_run_resumes_with_history_and_cost | `-p`, puis `--resume -p` | CA-S33 — run headless non enregistré ; reprise sans historique ou sans coût cumulé ; `resumed` faux | integration | 2026-11-16 | active |
| T-0120 | tests/test_headless.py › test_no_session_option_records_nothing_and_leaves_no_saved_output | `-p --no-session`, `--sessions` | CA-S34, ADR-0012 §5 — session créée malgré `--no-session` ; sortie enregistrée laissée sous `.harness/outputs/` | integration | 2026-11-16 | active |
| T-0121 | tests/test_headless.py › test_action_error_followed_by_an_answer_exits_0_and_the_error_is_in_the_stream | `-p --output-format jsonl` | CA-S35 — erreur d'action qui change le code ; erreur absente du flux ou non reliée à son appel | integration | 2026-11-16 | active |
| T-0122 | tests/test_headless.py › test_provider_lost_mid_run_exits_1_with_the_cause_and_the_session_is_resumable | `-p --output-format jsonl`, `--resume -p` | CA-S36 — mauvais code ou ligne finale sans statut/cause ; session perdue ou non reprenable | integration | 2026-11-16 | active |
| T-0123 | tests/test_headless.py › test_limit_reached_exits_3_without_asking_and_the_session_is_resumable | `-p` (jsonl et texte), `--resume -p` | CA-S37 + spec §6 (budget déjà dépassé à la reprise : code 3 sans appel) + ADR « Points confirmés » (stdout texte vide si code non nul) — question « continuer ? » posée ; run non arrêté ; limite non indiquée (paramétré ×2 : étapes/jsonl, budget/texte) | integration | 2026-11-16 | active |
| T-0124 | tests/test_headless.py › test_unusable_start_exits_2_with_nothing_run_nor_recorded | `cli.main.main` (headless) | CA-S38 — démarrage impossible avec un autre code, du texte sur stdout, une action exécutée ou un journal créé/modifié (paramétré ×8 : option invalide, prompt absent, config invalide, clé manquante, serveur injoignable, session inconnue, corrompue, autre dossier ; occupée : T-0101) | integration | 2026-11-16 | active |
| T-0125 | tests/test_headless_process.py › test_signal_during_a_long_command_kills_it_exits_130_and_records_the_interruption | vrai sous-processus + vrai signal, puis `--resume -p` | CA-S39 — commande longue survivante ; code autre que 130 ; ligne finale absente ; interruption non enregistrée ; session non reprenable (paramétré ×2 : SIGINT, SIGTERM) | e2e | 2026-11-16 | active |

## specs/003-sessions-et-mode-headless.md — écarts relevés en revue (échec d'écriture, réponse finale, tranches, verrou perdu, secret court)

| ID | Test (file › name) | Seam | Covers | Kind | Added | Status |
|---|---|---|---|---|---|---|
| T-0126 | tests/test_sessions_review_gaps.py › test_journal_write_failure_makes_headless_exit_1_with_an_error_result | `-p --output-format jsonl`, journal rendu inscriptible-impossible en cours de run | ADR-0012 §2 « Échec d'écriture », §7 — exception jusqu'à `main`, code autre que 1, pas d'avertissement ni de `result` d'erreur | integration | 2026-11-16 | active |
| T-0127 | tests/test_sessions_review_gaps.py › test_journal_write_failure_in_the_repl_warns_and_the_conversation_goes_on | REPL via `cli.main.main` | ADR-0012 §2 « Échec d'écriture » — exception, absence d'avertissement, conversation perdue, sortie non propre | integration | 2026-11-16 | active |
| T-0128 | tests/test_sessions_review_gaps.py › test_headless_empty_final_message_does_not_promote_intermediate_text_to_answer | `-p` (texte et jsonl) | CA-S30, ADR-0012 §7 — texte intermédiaire présenté comme réponse finale (paramétré ×2) | integration | 2026-11-16 | active |
| T-0129 | tests/test_sessions_review_gaps.py › test_budget_slice_granted_in_the_repl_is_restored_when_the_session_is_resumed | REPL, puis `--resume` | spec §4.1, ADR-0012 §2 « Cumuls » — tranche accordée oubliée à la reprise (limite = budget initial) | integration | 2026-11-16 | active |
| T-0130 | tests/test_sessions_review_gaps.py › test_process_that_lost_its_session_lock_no_longer_writes_to_the_journal | `-p`, verrou repris par un autre pendant le run | ADR-0012 §3.2 — détenteur évincé qui écrit encore ; verrou d'autrui supprimé ; code ≠ 1 | integration | 2026-11-16 | active |
| T-0131 | tests/test_sessions_review_gaps.py › test_very_short_secret_never_makes_a_journal_line_unreadable | REPL, puis `--resume` | CA-S4, ADR-0012 §2 (masquage) — ligne de journal illisible ou reprise refusée avec un secret d'un caractère (paramétré ×4 : `"`, `\`, `n`, `1`) | integration | 2026-11-16 | active |
