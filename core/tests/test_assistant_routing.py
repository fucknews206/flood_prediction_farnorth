"""Focused regression tests for the Far North conversational router.

These tests stub the authoritative engine and final LLM so they verify routing
and context boundaries without making network calls or depending on model text.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flood_prediction import server


async def _fake_synthesis(question, data, instruction, fallback, model=None):
    return f"LLM:{question}|context_keys={','.join(sorted(data))}"


class AssistantRoutingTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        server._assistant_session_context.clear()

    async def test_locality_query_preserves_original_question_and_structured_result(self):
        payload = {"locality": "Yagoua", "risk_level": "HIGH", "estimated_risk_percent": 78.0}
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis) as synth:
            result = await server._route_nat_intent(server.NATChatMessage(
                message="Résume sans pourcentages pour Yagoua", location="Cameroon"))

        self.assertEqual(result["status"], "ROUTED_LOCALITY")
        self.assertTrue(result["output"].startswith("LLM:Résume sans pourcentages"))
        context = synth.call_args.args[1]
        self.assertEqual(context["requested_locality"], "Yagoua")
        self.assertEqual(context["prediction"], payload)

    async def test_conceptual_soil_question_with_locality_does_not_call_risk_tool(self):
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            result = await server._route_nat_intent(server.NATChatMessage(
                message="What does soil moisture mean in Yagoua?", location="Cameroon"))
        self.assertEqual(result["status"], "llm_synthesized_knowledge")

    async def test_yaeres_is_not_silently_resolved_to_yagoua(self):
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            result = await server._route_nat_intent(server.NATChatMessage(
                message="Parle-moi des pêcheurs dans les Yaérés.", location="Cameroon"))
        self.assertEqual(result["status"], "llm_synthesized_domain")
        self.assertNotIn("Yagoua", result["output"])

    async def test_followup_uses_only_verified_context_locality(self):
        payload = {"locality": "Yagoua", "risk_level": "HIGH", "estimated_risk_percent": 78.0}
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            result = await server._route_nat_intent(server.NATChatMessage(
                message="Why?", location="Cameroon",
                context={"locality": "Yagoua", "prediction": payload}))
        self.assertEqual(result["status"], "ROUTED_FOLLOW_UP")
        risk.assert_called_once_with("Yagoua")

    async def test_followup_context_survives_without_client_context(self):
        payload = {"locality": "Yagoua", "risk_level": "HIGH", "estimated_risk_percent": 78.0}
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            first = await server.chat_with_ai("session-test", server.ChatMessage(
                message="What is the flood risk in Yagoua?", context={}))
            second = await server.chat_with_ai("session-test", server.ChatMessage(
                message="Why?", context={}))
        self.assertIn("Yagoua", server._assistant_session_context["session-test"]["locality"])
        self.assertIn("prediction", server._assistant_session_context["session-test"])
        self.assertGreaterEqual(risk.call_count, 2)

    async def test_generic_sentences_never_match_locality_fragments(self):
        generic = [
            "Primary drivers of flooding?",
            "Compare the impact of rainfall and rivers.",
            "Provide general safety guidance.",
            "Generate a preparedness checklist.",
            "Explain the main flood mechanisms.",
        ]
        with patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            for message in generic:
                result = await server._route_nat_intent(server.NATChatMessage(message=message))
                self.assertNotIn(result["status"], {"ROUTED_LOCALITY", "ROUTED_FORECAST", "ROUTED_DIVISION"})

    async def test_ranking_quantity_parser_honours_requested_count(self):
        rows = [{"name": f"Town {i}", "susceptibility_score": i, "historical_verified_event_count": 0}
                for i in range(1, 6)]
        with patch.object(server, "_get_farnorth_top_risk", return_value={"results": rows}), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            for message, expected in (("give me one locality", 1), ("top 3 areas", 3), ("just two", 2)):
                result = await server._route_nat_intent(server.NATChatMessage(message=message))
                self.assertEqual(server._ranking_count(message), expected)
                self.assertEqual(result["status"], "ROUTED_RANKING")

    async def test_conceptual_dyke_and_yaeres_questions_do_not_call_risk(self):
        questions = ["Qu'est-ce qu'une digue ?", "Qu'est-ce que les Yaérés ?"]
        with patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            for message in questions:
                result = await server._route_nat_intent(server.NATChatMessage(message=message))
                self.assertIn(result["status"], {"llm_synthesized_knowledge", "llm_synthesized_domain"})

    # =========================================================================
    # 10 EXACT VALIDATION SCENARIOS REQUIRED BY AUDIT SPECIFICATION
    # =========================================================================

    async def test_scenario_01_resume_sans_pourcentages_pour_yagoua(self):
        """TEST 1: 'Résume sans pourcentages pour Yagoua'
        Router: intent=FLOOD_RISK_QUERY, resolved_location='Yagoua', requires_prediction_data=True, tool=get_locality_risk.
        Instruction explicitly requests no percentages. Fallback also omits % signs.
        """
        payload = {
            "locality": "Yagoua",
            "risk_level": "HIGH",
            "estimated_risk_percent": 78.0,
            "confidence_score": 0.85,
        }
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis) as synth:
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Résume sans pourcentages pour Yagoua", location="Cameroon"
                ))

        risk.assert_called_once_with("Yagoua")
        self.assertEqual(result["status"], "ROUTED_LOCALITY")
        # Verify log output matches specification
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertTrue(len(router_logs) > 0)
        self.assertIn("intent=FLOOD_RISK_QUERY", router_logs[0])
        self.assertIn("resolved_location=Yagoua", router_logs[0])
        self.assertIn("requires_prediction_data=True", router_logs[0])
        self.assertIn("tool_called=True", router_logs[0])
        self.assertIn("tool_name=get_locality_risk", router_logs[0])

        # Verify synth instructions and context
        synth_args = synth.call_args.args
        self.assertIn("NO percentages", synth_args[2])
        self.assertEqual(synth_args[1]["requested_locality"], "Yagoua")
        self.assertEqual(synth_args[1]["prediction"], payload)

        # Verify fallback omits % signs as well
        fb = server._locality_fallback("Yagoua", payload, "Résume sans pourcentages pour Yagoua")
        self.assertNotIn("%", fb)
        self.assertNotIn("78", fb)

    async def test_scenario_02_quel_est_le_risque_a_yagoua(self):
        """TEST 2: 'Quel est le risque d'inondation à Yagoua ?'
        Router: intent=FLOOD_RISK_QUERY, resolved_location='Yagoua', requires_prediction_data=True, tool=get_locality_risk.
        """
        payload = {"locality": "Yagoua", "risk_level": "HIGH", "estimated_risk_percent": 75.0}
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Quel est le risque d'inondation à Yagoua ?"
                ))

        risk.assert_called_once_with("Yagoua")
        self.assertEqual(result["status"], "ROUTED_LOCALITY")
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertIn("intent=FLOOD_RISK_QUERY", router_logs[0])
        self.assertIn("resolved_location=Yagoua", router_logs[0])
        self.assertIn("tool_called=True", router_logs[0])

    async def test_scenario_03_que_signifie_humidite_du_sol_0_38(self):
        """TEST 3: 'Que signifie une humidité du sol de 0.38 ?'
        Conceptual question: intent=GENERAL_CONCEPTUAL, requires_prediction_data=False, tool_called=False.
        Does NOT require locality and does NOT call risk tool.
        """
        with patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Que signifie une humidité du sol de 0.38 ?"
                ))

        self.assertEqual(result["status"], "llm_synthesized_knowledge")
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertIn("intent=GENERAL_CONCEPTUAL", router_logs[0])
        self.assertIn("requires_prediction_data=False", router_logs[0])
        self.assertIn("tool_called=False", router_logs[0])

    async def test_scenario_04_quest_ce_quune_digue(self):
        """TEST 4: 'Qu'est-ce qu'une digue ?'
        Conceptual question: intent=GENERAL_CONCEPTUAL, requires_prediction_data=False, tool_called=False.
        """
        with patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Qu'est-ce qu'une digue ?"
                ))

        self.assertEqual(result["status"], "llm_synthesized_knowledge")
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertIn("intent=GENERAL_CONCEPTUAL", router_logs[0])
        self.assertIn("requires_prediction_data=False", router_logs[0])
        self.assertIn("tool_called=False", router_logs[0])

    async def test_scenario_05_pourquoi_maga_est_il_a_risque_eleve(self):
        """TEST 5: 'Pourquoi Maga est-il à risque élevé ?'
        Explanation question: intent=PREDICTION_EXPLANATION, resolved_location='Maga', requires_prediction_data=True, tool=get_locality_risk.
        """
        payload = {
            "locality": "Maga",
            "risk_level": "HIGH",
            "estimated_risk_percent": 82.0,
            "susceptibility_score": 7.8,
            "river_distance_km": 1.2,
        }
        with patch.object(server, "_farnorth_names", return_value=["Maga"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis) as synth:
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Pourquoi Maga est-il à risque élevé ?"
                ))

        risk.assert_called_once_with("Maga")
        self.assertEqual(result["status"], "ROUTED_LOCALITY")
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertIn("intent=PREDICTION_EXPLANATION", router_logs[0])
        self.assertIn("resolved_location=Maga", router_logs[0])
        self.assertIn("requires_prediction_data=True", router_logs[0])
        synth_args = synth.call_args.args
        self.assertIn("factors", synth_args[2].lower())

    async def test_scenario_06_et_pour_kousseri(self):
        """TEST 6: 'Et pour Kousséri ?'
        Short locality switch: intent=FLOOD_RISK_QUERY, resolved_location='Kousséri', requires_prediction_data=True, tool=get_locality_risk.
        """
        payload = {"locality": "Kousséri", "risk_level": "VERY_HIGH", "estimated_risk_percent": 91.0}
        with patch.object(server, "_farnorth_names", return_value=["Kousséri"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Et pour Kousséri ?"
                ))

        risk.assert_called_once_with("Kousséri")
        self.assertEqual(result["status"], "ROUTED_LOCALITY")
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertIn("intent=FLOOD_RISK_QUERY", router_logs[0])
        self.assertTrue("resolved_location=Kousséri" in router_logs[0] or "resolved_location=Kouss\\u00e9ri" in router_logs[0])
        self.assertIn("tool_called=True", router_logs[0])

    async def test_scenario_07_parle_moi_des_pecheurs_dans_les_yaeres(self):
        """TEST 7: 'Parle-moi des pêcheurs dans les Yaérés.'
        Location info: intent=LOCATION_INFORMATION, resolved_location='Yaérés', prediction_location=None.
        Does NOT call risk tool. Never substitutes Yagoua!
        """
        with patch.object(server, "_farnorth_names", return_value=["Yagoua", "Maga"]), \
             patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis) as synth:
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Parle-moi des pêcheurs dans les Yaérés."
                ))

        self.assertEqual(result["status"], "llm_synthesized_domain")
        self.assertNotIn("Yagoua", result["output"])
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertIn("intent=LOCATION_INFORMATION", router_logs[0])
        self.assertTrue("resolved_location=Yaérés" in router_logs[0] or "resolved_location=Ya\\u00e9r\\u00e9s" in router_logs[0])
        self.assertIn("requires_prediction_data=False", router_logs[0])
        self.assertIn("tool_called=False", router_logs[0])
        synth_args = synth.call_args.args
        self.assertIn("fishermen", synth_args[1].get("fishermen_situation", "").lower())
        self.assertIn("Do NOT substitute Yagoua", synth_args[2])

    async def test_scenario_08_quest_ce_que_les_yaeres(self):
        """TEST 8: 'Qu'est-ce que les Yaérés ?'
        Conceptual query on geographic area: intent=GENERAL_CONCEPTUAL, resolved_location='Yaérés', prediction_location=None.
        Does NOT call risk tool. Never substitutes Yagoua!
        """
        with patch.object(server, "_farnorth_names", return_value=["Yagoua", "Maga"]), \
             patch.object(server, "_get_farnorth_risk", side_effect=AssertionError("risk tool called")), \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            with self.assertLogs("flood_prediction.settings", level="INFO") as cm:
                result = await server._route_nat_intent(server.NATChatMessage(
                    message="Qu'est-ce que les Yaérés ?"
                ))

        self.assertIn(result["status"], {"llm_synthesized_knowledge", "llm_synthesized_domain"})
        self.assertNotIn("Yagoua", result["output"])
        router_logs = [l for l in cm.output if "[AI ROUTER]" in l]
        self.assertIn("requires_prediction_data=False", router_logs[0])
        self.assertIn("tool_called=False", router_logs[0])

    async def test_scenario_09_flood_risk_in_yagoua_then_why(self):
        """TEST 9: Multi-turn: 'What is the flood risk in Yagoua?' -> 'Why?'
        Turn 1: resolves Yagoua, calls get_locality_risk.
        Turn 2: keeps Yagoua context without asking for locality, intent=FOLLOW_UP_TO_PREVIOUS_RESULT.
        """
        payload = {"locality": "Yagoua", "risk_level": "HIGH", "estimated_risk_percent": 78.0}
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            session_id = "test-session-multi-09"
            first = await server.chat_with_ai(session_id, server.ChatMessage(
                message="What is the flood risk in Yagoua?"
            ))
            self.assertEqual(server._assistant_session_context[session_id]["locality"], "Yagoua")

            second = await server.chat_with_ai(session_id, server.ChatMessage(
                message="Why?"
            ))
            self.assertTrue(second.response.startswith("LLM:Why?"))
            self.assertGreaterEqual(risk.call_count, 2)

            # Also verify via direct NAT router route
            routed_followup = await server._route_nat_intent(server.NATChatMessage(
                message="Why?", context={"locality": "Yagoua", "prediction": payload}
            ))
            self.assertEqual(routed_followup["status"], "ROUTED_FOLLOW_UP")

    async def test_scenario_10_flood_risk_in_yagoua_then_what_does_soil_moisture_mean(self):
        """TEST 10: Multi-turn: 'What is the flood risk in Yagoua?' -> 'What does soil moisture mean?'
        Turn 1: resolves Yagoua, calls get_locality_risk.
        Turn 2: recognizes conceptual shift, intent=GENERAL_CONCEPTUAL, does NOT call risk tool.
        """
        payload = {"locality": "Yagoua", "risk_level": "HIGH", "estimated_risk_percent": 78.0}
        with patch.object(server, "_farnorth_names", return_value=["Yagoua"]), \
             patch.object(server, "_get_farnorth_risk", return_value=payload) as risk, \
             patch.object(server, "_llm_synthesize", side_effect=_fake_synthesis):
            session_id = "test-session-multi-10"
            first = await server.chat_with_ai(session_id, server.ChatMessage(
                message="What is the flood risk in Yagoua?"
            ))
            self.assertEqual(risk.call_count, 1)

            # Turn 2: Conceptual question; risk tool must NOT be called again
            second = await server.chat_with_ai(session_id, server.ChatMessage(
                message="What does soil moisture mean?"
            ))
            self.assertTrue(second.response.startswith("LLM:What does soil moisture mean?"))
            self.assertEqual(risk.call_count, 1)  # Risk count stayed at 1!

            # Also verify via direct NAT router route
            routed_concept = await server._route_nat_intent(server.NATChatMessage(
                message="What does soil moisture mean?", context={"locality": "Yagoua", "prediction": payload}
            ))
            self.assertEqual(routed_concept["status"], "llm_synthesized_knowledge")


if __name__ == "__main__":
    unittest.main()
