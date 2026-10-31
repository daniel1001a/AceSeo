# GEO evidence report

Run: run_20261019T210001Z_6f7d91 (transport fixture)

## Recommendation

GEO first: fix facts. The same claim that contradicts the site's own facts, or repeats a value the facts mark as outdated, appears in enough answers to pass the reproduction threshold. Make the correct fact easier to find and quote. (draft wording, not yet reviewed against a live run) The deciding rule is the reproduced fact contradictions rule. Decision record: [dec_site_d9c5630060e9fcf0]. All thresholds are provisional, fixed for the first live run but not yet calibrated against real data; the decision record keeps their values.

## Rule evaluations

- blocking SEO checks on key pages: not_fired (blocking_checks_pass). Read: [pc_http-status_7c032be60e15f406], [pc_http-status_f47a15ae149623da], [pc_http-status_ff2857054f0fc172], [pc_key-content_bb5e2e966e9fa241], [pc_main-content_60bb7ea739fc48f0], [pc_main-content_efc4e5f0b76a5a4d], [pc_noindex_1b078a568845fb9b], [pc_noindex_9b296a32390aef87], [pc_noindex_d4492b880bd90a52], [pc_robots-ai_01243cb17f0929dd], [pc_robots-ai_01a5e88bc867e933], [pc_robots-ai_0ca32da22608177c], [pc_robots-ai_2297cd427770d475], [pc_robots-ai_329daad9987a7ead], [pc_robots-ai_41dbc64c7b8e4933], [pc_robots-ai_465f95a16591f20d], [pc_robots-ai_4f0df217f37f3178], [pc_robots-ai_63ddb9db05d3d795], [pc_robots-ai_7865bc4d203bb480], [pc_robots-ai_8bcd6f96270e8fe7], [pc_robots-ai_997e57e21d2e6bfa], [pc_robots-ai_a45b3831e4a78de1], [pc_robots-ai_a7aecf12aa5284a9], [pc_robots-ai_c1239c0f21246246], [pc_robots-ai_d99c34a545faf634], [pc_robots-ai_e2b1238762129642], [pc_robots-ai_f52d16a94b538ec8], [pc_robots-ai_f9ba4a4b56bedfe7], [pc_robots-ai_fadc209c59f7dbfc], [pc_robots-ai_fde4e5e4ac8aa2ce]
- evidence gate: not_fired (engines_sufficient). Read: [cap_anthropic_2b1d0e3b4f85174b], [cap_anthropic_31ffa694bd40ea94], [cap_anthropic_3b6300be72aea962], [cap_anthropic_843c705a7aa502fc], [cap_anthropic_876bea7124cce19e], [cap_anthropic_e7d57ec13917f052], [cap_openai_1e00a1188f489219], [cap_openai_4e5d3f3666a344d1], [cap_openai_6444696b0eb41c5a], [cap_openai_e6306c0e7c266d15], [cap_openai_f7b363feeebc2eb4], [cap_openai_fbe76378c5a90721]
- reproduced fact contradictions: fired (contradiction_reproduced). Read: [cap_anthropic_2b1d0e3b4f85174b], [cap_anthropic_31ffa694bd40ea94], [cap_anthropic_3b6300be72aea962], [cap_anthropic_843c705a7aa502fc], [cap_anthropic_876bea7124cce19e], [cap_anthropic_e7d57ec13917f052], [cap_openai_1e00a1188f489219], [cap_openai_4e5d3f3666a344d1], [cap_openai_6444696b0eb41c5a], [cap_openai_e6306c0e7c266d15], [cap_openai_f7b363feeebc2eb4], [cap_openai_fbe76378c5a90721], [clm_anthropic_4840677f9b118917], [clm_anthropic_55c6cb56214b2812], [clm_anthropic_7618eec8d5064c9f], [clm_anthropic_9aa71592b42405e1], [clm_anthropic_bc527104063c89d4], [clm_anthropic_d6837f8197d8bd0e], [clm_openai_119e7b3886b8c968], [clm_openai_477565e902d00214], [clm_openai_9419837ead4af7bc], [clm_openai_a588d4d139f4f46b], [clm_openai_c68dc0ee00da9b3e], [clm_openai_f04236f37d960f0d]
- low citation across vendors: not_evaluated (cascade_stopped).
- no other rule fired: not_evaluated (cascade_stopped).

## Measurements

- 0 (n=30) [Measured] {blocking_fail.key_pages; evidence: pc_http-status_7c032be60e15f406, pc_http-status_f47a15ae149623da, pc_http-status_ff2857054f0fc172, pc_key-content_bb5e2e966e9fa241, pc_main-content_60bb7ea739fc48f0, pc_main-content_efc4e5f0b76a5a4d, pc_noindex_1b078a568845fb9b, pc_noindex_9b296a32390aef87, pc_noindex_d4492b880bd90a52, pc_robots-ai_01243cb17f0929dd, pc_robots-ai_01a5e88bc867e933, pc_robots-ai_0ca32da22608177c, pc_robots-ai_2297cd427770d475, pc_robots-ai_329daad9987a7ead, pc_robots-ai_41dbc64c7b8e4933, pc_robots-ai_465f95a16591f20d, pc_robots-ai_4f0df217f37f3178, pc_robots-ai_63ddb9db05d3d795, pc_robots-ai_7865bc4d203bb480, pc_robots-ai_8bcd6f96270e8fe7, pc_robots-ai_997e57e21d2e6bfa, pc_robots-ai_a45b3831e4a78de1, pc_robots-ai_a7aecf12aa5284a9, pc_robots-ai_c1239c0f21246246, pc_robots-ai_d99c34a545faf634, pc_robots-ai_e2b1238762129642, pc_robots-ai_f52d16a94b538ec8, pc_robots-ai_f9ba4a4b56bedfe7, pc_robots-ai_fadc209c59f7dbfc, pc_robots-ai_fde4e5e4ac8aa2ce; window 2026-10-19T21:00:02.000000Z..2026-10-19T21:00:28.000000Z}
- 3/3 [Measured] {citation_rate.engine_prompt; engine anthropic; prompt_id p_01; evidence: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_876bea7124cce19e; hits: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_876bea7124cce19e; window 2026-10-19T21:00:40.000000Z..2026-10-19T21:00:44.000000Z}
- 3/3 [Measured] {mention_rate.engine_prompt; engine anthropic; prompt_id p_01; evidence: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_876bea7124cce19e; hits: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_876bea7124cce19e; window 2026-10-19T21:00:40.000000Z..2026-10-19T21:00:44.000000Z}
- 3/3 [Measured] {citation_rate.engine_prompt; engine anthropic; prompt_id p_02; evidence: cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_e7d57ec13917f052; hits: cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_e7d57ec13917f052; window 2026-10-19T21:00:46.000000Z..2026-10-19T21:00:50.000000Z}
- 3/3 [Measured] {mention_rate.engine_prompt; engine anthropic; prompt_id p_02; evidence: cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_e7d57ec13917f052; hits: cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_e7d57ec13917f052; window 2026-10-19T21:00:46.000000Z..2026-10-19T21:00:50.000000Z}
- 6/6 [Measured] {citation_rate.engine; engine anthropic; evidence: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_876bea7124cce19e, cap_anthropic_e7d57ec13917f052; hits: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_876bea7124cce19e, cap_anthropic_e7d57ec13917f052; window 2026-10-19T21:00:40.000000Z..2026-10-19T21:00:50.000000Z}
- 6/6 [Measured] {contradiction_rate.engine; engine anthropic; evidence: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_876bea7124cce19e, cap_anthropic_e7d57ec13917f052; hits: cap_anthropic_2b1d0e3b4f85174b, cap_anthropic_31ffa694bd40ea94, cap_anthropic_3b6300be72aea962, cap_anthropic_843c705a7aa502fc, cap_anthropic_876bea7124cce19e, cap_anthropic_e7d57ec13917f052; window 2026-10-19T21:00:40.000000Z..2026-10-19T21:00:50.000000Z}
- 3/3 [Measured] {citation_rate.engine_prompt; engine openai; prompt_id p_01; evidence: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a; hits: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a; window 2026-10-19T21:00:52.000000Z..2026-10-19T21:00:56.000000Z}
- 3/3 [Measured] {mention_rate.engine_prompt; engine openai; prompt_id p_01; evidence: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a; hits: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a; window 2026-10-19T21:00:52.000000Z..2026-10-19T21:00:56.000000Z}
- 3/3 [Measured] {citation_rate.engine_prompt; engine openai; prompt_id p_02; evidence: cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; hits: cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; window 2026-10-19T21:00:58.000000Z..2026-10-19T21:01:02.000000Z}
- 3/3 [Measured] {mention_rate.engine_prompt; engine openai; prompt_id p_02; evidence: cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; hits: cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; window 2026-10-19T21:00:58.000000Z..2026-10-19T21:01:02.000000Z}
- 6/6 [Measured] {citation_rate.engine; engine openai; evidence: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a, cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; hits: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a, cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; window 2026-10-19T21:00:52.000000Z..2026-10-19T21:01:02.000000Z}
- 6/6 [Measured] {contradiction_rate.engine; engine openai; evidence: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a, cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; hits: cap_openai_1e00a1188f489219, cap_openai_4e5d3f3666a344d1, cap_openai_6444696b0eb41c5a, cap_openai_e6306c0e7c266d15, cap_openai_f7b363feeebc2eb4, cap_openai_fbe76378c5a90721; window 2026-10-19T21:00:52.000000Z..2026-10-19T21:01:02.000000Z}

## Independence groups

- site:www.boardflight.com: [pc_http-status_7c032be60e15f406], [pc_http-status_f47a15ae149623da], [pc_http-status_ff2857054f0fc172], [pc_key-content_bb5e2e966e9fa241], [pc_main-content_60bb7ea739fc48f0], [pc_main-content_efc4e5f0b76a5a4d], [pc_noindex_1b078a568845fb9b], [pc_noindex_9b296a32390aef87], [pc_noindex_d4492b880bd90a52], [pc_robots-ai_01243cb17f0929dd], [pc_robots-ai_01a5e88bc867e933], [pc_robots-ai_0ca32da22608177c], [pc_robots-ai_2297cd427770d475], [pc_robots-ai_329daad9987a7ead], [pc_robots-ai_41dbc64c7b8e4933], [pc_robots-ai_465f95a16591f20d], [pc_robots-ai_4f0df217f37f3178], [pc_robots-ai_63ddb9db05d3d795], [pc_robots-ai_7865bc4d203bb480], [pc_robots-ai_8bcd6f96270e8fe7], [pc_robots-ai_997e57e21d2e6bfa], [pc_robots-ai_a45b3831e4a78de1], [pc_robots-ai_a7aecf12aa5284a9], [pc_robots-ai_c1239c0f21246246], [pc_robots-ai_d99c34a545faf634], [pc_robots-ai_e2b1238762129642], [pc_robots-ai_f52d16a94b538ec8], [pc_robots-ai_f9ba4a4b56bedfe7], [pc_robots-ai_fadc209c59f7dbfc], [pc_robots-ai_fde4e5e4ac8aa2ce]
- vendor:anthropic: [cap_anthropic_2b1d0e3b4f85174b], [cap_anthropic_31ffa694bd40ea94], [cap_anthropic_3b6300be72aea962], [cap_anthropic_843c705a7aa502fc], [cap_anthropic_876bea7124cce19e], [cap_anthropic_e7d57ec13917f052], [clm_anthropic_4840677f9b118917], [clm_anthropic_55c6cb56214b2812], [clm_anthropic_7618eec8d5064c9f], [clm_anthropic_9aa71592b42405e1], [clm_anthropic_bc527104063c89d4], [clm_anthropic_d6837f8197d8bd0e]
- vendor:openai: [cap_openai_1e00a1188f489219], [cap_openai_4e5d3f3666a344d1], [cap_openai_6444696b0eb41c5a], [cap_openai_e6306c0e7c266d15], [cap_openai_f7b363feeebc2eb4], [cap_openai_fbe76378c5a90721], [clm_openai_119e7b3886b8c968], [clm_openai_477565e902d00214], [clm_openai_9419837ead4af7bc], [clm_openai_a588d4d139f4f46b], [clm_openai_c68dc0ee00da9b3e], [clm_openai_f04236f37d960f0d]

## Contradicted or outdated claims

- [clm_anthropic_4840677f9b118917] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_anthropic_2b1d0e3b4f85174b]
- [clm_anthropic_bc527104063c89d4] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_anthropic_31ffa694bd40ea94]
- [clm_anthropic_55c6cb56214b2812] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_anthropic_3b6300be72aea962]
- [clm_anthropic_d6837f8197d8bd0e] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_anthropic_843c705a7aa502fc]
- [clm_anthropic_9aa71592b42405e1] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_anthropic_876bea7124cce19e]
- [clm_anthropic_7618eec8d5064c9f] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_anthropic_e7d57ec13917f052]
- [clm_openai_119e7b3886b8c968] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_openai_1e00a1188f489219]
- [clm_openai_a588d4d139f4f46b] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_openai_4e5d3f3666a344d1]
- [clm_openai_9419837ead4af7bc] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_openai_6444696b0eb41c5a]
- [clm_openai_c68dc0ee00da9b3e] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_openai_e6306c0e7c266d15]
- [clm_openai_f04236f37d960f0d] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_openai_f7b363feeebc2eb4]
- [clm_openai_477565e902d00214] is contradicted against fact [fct_3a18902f276b9006], in capture [cap_openai_fbe76378c5a90721]

## Excluded and skipped

- no failed or refused attempts
- skipped slot perplexity p_01 repeat 0: terms_gate
- skipped slot perplexity p_01 repeat 1: terms_gate
- skipped slot perplexity p_01 repeat 2: terms_gate
- skipped slot perplexity p_02 repeat 0: terms_gate
- skipped slot perplexity p_02 repeat 1: terms_gate
- skipped slot perplexity p_02 repeat 2: terms_gate
- skipped slot xai p_01 repeat 0: terms_gate
- skipped slot xai p_01 repeat 1: terms_gate
- skipped slot xai p_01 repeat 2: terms_gate
- skipped slot xai p_02 repeat 0: terms_gate
- skipped slot xai p_02 repeat 1: terms_gate
- skipped slot xai p_02 repeat 2: terms_gate
- engine perplexity excluded: opt_in_not_selected (terms_status verified-allowed)
- engine xai excluded: terms_unverified (terms_status unverified)

## Not checked

- consumer_ui_answers: Answers shown inside consumer apps and search result pages were not observed.
- personalization_location: Personalisation, location and conversation history were not varied.
- logged_in_surfaces: Logged-in, app-only and paid surfaces were not observed.
- engines_not_configured: Engines that are not configured for this run were not queried.
- traffic_ranking_outcomes: Traffic, ranking and conversion outcomes were not measured.
- gemini_grounding_excluded: Gemini grounding with Google Search is excluded because its terms forbid storing or analysing grounded results.
- engine_excluded: perplexity (opt_in_not_selected)
- engine_excluded: xai (terms_unverified)
- skipped_slots: listed under Excluded and skipped

---
These results describe API-model behaviour: answers returned by the configured models through their official APIs. They are not what users of consumer apps see (PLAN assumption A7).
