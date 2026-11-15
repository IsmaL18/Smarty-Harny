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
| T-0078 | tests/test_long_outputs.py › test_saved_outputs_are_deleted_when_the_session_ends | `cli.repl.run` | CA-44 — sorties enregistrées laissées après `/quit` ou Ctrl+D (paramétré ×2) | e2e | 2026-11-15 | active |
| T-0079 | tests/test_long_outputs.py › test_stale_session_folders_are_purged_at_launch_but_recent_ones_are_kept | `cli.repl.run` | ADR-0011 §12 — restes de crash conservés ; session concurrente supprimée | e2e | 2026-11-15 | active |
| T-0080 | tests/test_edit_display.py › test_successful_edit_shows_a_title_then_the_diff_in_detailed_mode | `cli.repl.run` | CA-52 — nombre de remplacements absent ; diff absent ou toujours affiché | e2e | 2026-11-15 | active |
| T-0081 | tests/test_edit_file.py › test_multiline_tolerant_match_must_cover_whole_lines | `Session.run_turn` (edit_file) | ADR-0010 §8 — remplacement en milieu de ligne sur plusieurs lignes ; fichier modifié à tort | integration | 2026-11-15 | active |
| T-0082 | tests/test_edit_file.py › test_multiline_match_on_whole_lines_tolerates_a_different_indentation | `Session.run_turn` (edit_file) | ADR-0010 §8 — lignes entières à indentation différente refusées à tort | integration | 2026-11-15 | active |
| T-0083 | tests/test_edit_file.py › test_single_line_tolerant_match_in_mid_line_is_still_accepted | `Session.run_turn` (edit_file) | ADR-0010 §8 — tolérance mono-ligne en milieu de ligne supprimée par la correction | integration | 2026-11-15 | active |
