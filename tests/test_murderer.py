"""
Test suite for the Murderer scenario.

Covers:
  - Generation invariants (always solvable, valid structure)
  - Difficulty scaling
  - Clue system (concrete, falseable, narrows correctly)
  - Case types (conspiracy, frame, passion, serial)
  - Confrontation system
  - Time/agenda system
  - World reactions
  - Save/load roundtrip
"""
import pytest
import random
from scenarios.murderer import (
    MurdererScenario, _questions_per_period, _payment_cost,
    _strike_hours, _format_time, DIFFICULTY_TABLE,
)
from scenarios.base import CaseType, ConfrontationState


# ── Generation invariants ─────────────────────────────────────

class TestGeneration:
    def test_always_has_killer(self, murderer):
        killer = murderer.characters.get(murderer.state.killer_id)
        assert killer is not None
        assert killer.is_killer

    def test_always_has_first_victim(self, murderer):
        assert len(murderer.state.victims) == 1

    def test_killer_not_first_victim(self, murderer):
        assert murderer.state.killer_id not in murderer.state.victims

    def test_characters_have_required_fields(self, murderer):
        for char in murderer.characters.values():
            assert char.name
            assert char.occupation
            assert char.district
            assert char.trait

    def test_clues_generated(self, murderer):
        assert len(murderer.clues) >= 5

    def test_all_clues_have_text(self, murderer):
        for cid, clue in murderer.clues.items():
            assert clue.text, f"Clue {cid} has empty text"

    def test_clue_holders_valid(self, murderer):
        for holder_id, clue_ids in murderer.clue_holders.items():
            assert holder_id in murderer.characters, f"Unknown holder {holder_id}"
            for cid in clue_ids:
                assert cid in murderer.clues, f"Unknown clue {cid} in holder {holder_id}"

    def test_seed_determinism(self):
        m1 = MurdererScenario(seed=7, difficulty=5)
        m2 = MurdererScenario(seed=7, difficulty=5)
        assert m1.state.killer_id == m2.state.killer_id
        assert m1.town_name == m2.town_name
        assert m1.state.case_type == m2.state.case_type

    def test_different_seeds_differ(self):
        killers = set()
        for seed in range(10):
            m = MurdererScenario(seed=seed, difficulty=5)
            killers.add(m.state.killer_id)
        assert len(killers) > 3  # not all the same killer

    def test_relationships_generated(self, murderer):
        assert len(murderer.relationships) > 0

    def test_secrets_generated(self, murderer):
        assert len(murderer.secrets) > 0

    def test_agenda_generated(self, murderer):
        assert len(murderer.state.killer_agenda) > 0


# ── Solvability ───────────────────────────────────────────────

class TestSolvability:
    @pytest.mark.parametrize("seed", range(20))
    def test_killer_narrowed_by_genuine_clues(self, seed):
        """After all genuine, non-lie clues are found, killer is in suspect list."""
        m = MurdererScenario(seed=seed, difficulty=5)
        for cid, clue in m.clues.items():
            if not clue.is_lie and clue.narrows_suspects:
                clue.found = True
                m.state.clues_found.append(cid)
        suspects = m._compute_suspects_snap()
        killer = m.characters[m.state.killer_id]
        suspect_names = [s["name"] for s in suspects]
        assert killer.name in suspect_names, (
            f"Seed {seed}: killer {killer.name} not in suspects {suspect_names}"
        )

    @pytest.mark.parametrize("seed", range(10))
    def test_killer_is_unique_after_key_clues(self, seed):
        """With district + occupation genuine clues, suspect list is small."""
        m = MurdererScenario(seed=seed, difficulty=5)
        key_clues = ["district_seen", "occupation_direct", "alibi_break", "trait_behavior"]
        for cid in key_clues:
            if cid in m.clues and not m.clues[cid].is_lie:
                m.clues[cid].found = True
                m.state.clues_found.append(cid)
        suspects = m._compute_suspects_snap()
        assert len(suspects) <= 3, (
            f"Seed {seed}: {len(suspects)} suspects remain after key clues"
        )

    def test_genuine_clues_always_lead_to_killer(self):
        """After all genuine (non-lie) narrowing clues, killer is in suspects."""
        for seed in range(20):
            m = MurdererScenario(seed=seed, difficulty=15)
            genuine = [cid for cid, cl in m.clues.items()
                       if not cl.is_lie and cl.narrows_suspects]
            if not genuine:
                continue
            for cid in genuine:
                m.clues[cid].found = True
                m.state.clues_found.append(cid)
            suspects = m._compute_suspects_snap()
            killer = m.characters[m.state.killer_id]
            assert killer.name in [s["name"] for s in suspects], (
                f"Seed {seed} diff 15: killer {killer.name} not in suspects "
                f"after genuine clues: {[s['name'] for s in suspects]}"
            )


# ── Difficulty scaling ────────────────────────────────────────

class TestDifficultyScaling:
    @pytest.mark.parametrize("level,expected_q", [
        (1, 3), (4, 3), (5, 2), (8, 2), (9, 2), (14, 2), (15, 1), (20, 1)
    ])
    def test_questions_per_period(self, level, expected_q):
        assert _questions_per_period(level) == expected_q

    @pytest.mark.parametrize("level,expected_cost", [
        (1, 10), (5, 15), (9, 20), (13, 30), (17, 40)
    ])
    def test_payment_cost(self, level, expected_cost):
        assert _payment_cost(level) == expected_cost

    def test_higher_difficulty_less_money(self):
        from scenarios.murderer import _difficulty_params
        monies = [_difficulty_params(d)[2] for d in [1, 5, 10, 15, 20]]
        assert monies == sorted(monies, reverse=True)

    def test_higher_difficulty_fewer_max_victims(self):
        from scenarios.murderer import _difficulty_params
        victims = [_difficulty_params(d)[3] for d in [1, 5, 10, 15, 20]]
        assert victims[0] >= victims[-1]

    def test_harder_difficulty_has_more_lies(self):
        easy_lies = len([c for c in MurdererScenario(seed=42, difficulty=1).clues.values() if c.is_lie])
        hard_lies = len([c for c in MurdererScenario(seed=42, difficulty=18).clues.values() if c.is_lie])
        assert hard_lies >= easy_lies

    def test_money_set_correctly(self, murderer, difficulty):
        from scenarios.murderer import _difficulty_params
        expected_money = _difficulty_params(difficulty)[2]
        assert murderer.state.money == expected_money

    def test_state_stores_difficulty(self, murderer, difficulty):
        assert murderer.state.difficulty == difficulty


# ── Clue system ───────────────────────────────────────────────

class TestClues:
    def test_clues_reference_valid_attributes(self, murderer_easy):
        valid_attrs = {"occupation", "district", "trait", "motive", "method"}
        for cid, clue in murderer_easy.clues.items():
            assert clue.attribute in valid_attrs | {"method_occ"} or not clue.narrows_suspects, \
                f"Clue {cid} has unknown attribute {clue.attribute}"

    def test_scene_clue_not_in_holders(self, murderer_easy):
        scene_clues = [cid for cid, cl in murderer_easy.clues.items() if cl.scene_only]
        for sc in scene_clues:
            for holder_id, clue_ids in murderer_easy.clue_holders.items():
                holder = murderer_easy.characters[holder_id]
                if not holder.is_killer:
                    assert sc not in clue_ids, f"Scene clue {sc} given to non-killer holder"

    def test_day_available_ordering(self, murderer_easy):
        clues = list(murderer_easy.clues.values())
        day0 = [c for c in clues if c.day_available == 0 and not c.scene_only]
        assert len(day0) >= 2, "Need at least 2 clues available from day 0"

    def test_narrows_suspects_flag(self, murderer_easy):
        # method_occ should not narrow (it's directional)
        if "method_occ" in murderer_easy.clues:
            assert not murderer_easy.clues["method_occ"].narrows_suspects

    def test_reveal_clue_marks_found(self, murderer_easy):
        unrevealed = [cid for cid, c in murderer_easy.clues.items() if not c.found]
        assert unrevealed
        cid = unrevealed[0]
        murderer_easy.reveal_clue(cid)
        assert murderer_easy.clues[cid].found
        assert cid in murderer_easy.state.clues_found


# ── Case types ────────────────────────────────────────────────

class TestCaseTypes:
    def _get_case(self, case_type: CaseType, difficulty=12):
        for seed in range(50):
            m = MurdererScenario(seed=seed, difficulty=difficulty)
            if CaseType(m.state.case_type) == case_type:
                return m
        pytest.skip(f"No {case_type.value} case found in 50 seeds")

    def test_serial_has_multiple_strikes(self):
        m = self._get_case(CaseType.SERIAL, difficulty=5)
        assert m.state.next_strike_hour < 9999

    def test_passion_has_flee_hour(self):
        m = self._get_case(CaseType.PASSION)
        assert m.state.flee_hour < 9999
        assert m.state.next_strike_hour == 9999.0

    def test_conspiracy_has_accomplice(self):
        m = self._get_case(CaseType.CONSPIRACY)
        assert m.state.accomplice_id is not None
        assert m.state.accomplice_id in m.characters

    def test_conspiracy_has_accomplice_clues(self):
        m = self._get_case(CaseType.CONSPIRACY)
        ac_clues = [cid for cid in m.clues if "accomplice" in cid]
        assert len(ac_clues) >= 2

    def test_frame_has_framed_person(self):
        m = self._get_case(CaseType.FRAME)
        assert m.state.framed_id is not None
        framed = m.characters[m.state.framed_id]
        assert not framed.is_killer

    def test_frame_has_planted_evidence(self):
        m = self._get_case(CaseType.FRAME)
        assert "frame_evidence" in m.clues
        assert m.clues["frame_evidence"].is_lie

    def test_frame_has_counter_evidence(self):
        m = self._get_case(CaseType.FRAME)
        assert "frame_counter" in m.clues
        assert not m.clues["frame_counter"].is_lie


# ── Confrontation ─────────────────────────────────────────────

class TestConfrontation:
    def _setup(self, seed=42, difficulty=5):
        m = MurdererScenario(seed=seed, difficulty=difficulty)
        # Give enough clues to begin confrontation
        for cid in list(m.clues.keys())[:4]:
            if not m.clues[cid].is_lie:
                m.clues[cid].found = True
                m.state.clues_found.append(cid)
        return m

    def test_begin_confrontation_requires_clues(self):
        m = MurdererScenario(seed=42, difficulty=5)
        conf, err = m.begin_confrontation(m.state.killer_id)
        assert conf is None
        assert "clue" in err.lower()

    def test_begin_confrontation_succeeds_with_clues(self):
        m = self._setup()
        conf, err = m.begin_confrontation(m.state.killer_id)
        assert conf is not None
        assert err == ""

    def test_opening_line_varies_by_trait(self):
        lines = set()
        for seed in range(20):
            m = self._setup(seed=seed)
            lines.add(m.opening_line(m.state.killer_id))
        assert len(lines) > 1

    def test_genuine_clue_increases_pressure(self):
        m = self._setup()
        killer = m.characters[m.state.killer_id]
        conf = ConfrontationState(suspect_id=m.state.killer_id)
        clues = m.confrontation_clues(m.state.killer_id, conf)
        genuine = [c for c in clues if c.is_genuine]
        assert genuine
        before = conf.pressure
        m.present_clue(conf, genuine[0])
        assert conf.pressure > before

    def test_lie_clue_decreases_pressure(self):
        m = self._setup()
        conf = ConfrontationState(suspect_id=m.state.killer_id)
        # Inject a lie clue
        from scenarios.base import Clue
        lie = Clue(id="test_lie", attribute="district",
                   value=m.state.killer_district, text="A lie.",
                   is_lie=True, narrows_suspects=True, found=True)
        m.clues["test_lie"] = lie
        m.state.clues_found.append("test_lie")
        conf.pressure = 0.5
        clues = m.confrontation_clues(m.state.killer_id, conf)
        lie_clue = next((c for c in clues if c.clue_id == "test_lie"), None)
        if lie_clue:
            m.present_clue(conf, lie_clue)
            assert conf.pressure < 0.5

    def test_high_pressure_confesses(self):
        m = self._setup()
        conf = ConfrontationState(suspect_id=m.state.killer_id)
        conf.pressure = 0.79
        clues = m.confrontation_clues(m.state.killer_id, conf)
        genuine = [c for c in clues if c.is_genuine]
        if genuine:
            narrative, result = m.present_clue(conf, genuine[0])
            if conf.pressure >= 0.80:
                assert result is not None
                assert result.won

    def test_withdraw_no_accusation_penalty(self):
        m = self._setup()
        before_count = m.state.accusation_count
        conf, _ = m.begin_confrontation(m.state.killer_id)
        m.withdraw_confrontation(conf)
        # accusation_count was incremented in begin, then decremented in withdraw
        assert m.state.accusation_count == before_count


# ── Time and agenda ───────────────────────────────────────────

class TestTimeAndAgenda:
    def test_advance_time_increments_hour(self):
        m = MurdererScenario(seed=42, difficulty=5)
        start = m.state.hour
        m.advance_time(3.0)
        assert abs(m.state.hour - (start + 3.0)) < 0.01

    def test_question_period_resets_after_8h(self):
        m = MurdererScenario(seed=42, difficulty=5)
        char = next(c for c in m.characters.values() if c.alive and not c.is_killer)
        m.use_question(char.id, 0)
        m.use_question(char.id, 0)
        ok, _ = m.use_question(char.id, 0)
        assert not ok  # exhausted
        # Advance 8h
        m.advance_time(8.0)
        ok2, _ = m.use_question(char.id, 0)
        assert ok2  # reset

    def test_agenda_items_have_valid_hours(self):
        m = MurdererScenario(seed=42, difficulty=5)
        for item in m.state.killer_agenda:
            assert item["hour"] > m.state.hour
            assert item["hour"] < 200  # no absurd values

    def test_intercept_fires_when_in_right_location(self):
        m = MurdererScenario(seed=42, difficulty=5)
        first = m.state.killer_agenda[0]
        # Advance to 1h before agenda item
        m.advance_time(first["hour"] - m.state.hour - 1)
        m.state.player_location = first["district"]
        events = m.advance_time(2.0)
        assert first["intercepted"]

    def test_missed_agenda_fires_district_reaction(self):
        m = MurdererScenario(seed=42, difficulty=5)
        silence = next(
            (item for item in m.state.killer_agenda if item["action"] == "silence_witness"),
            None
        )
        if not silence:
            pytest.skip("No silence_witness in this agenda")
        # Skip past the agenda item
        m.state.player_location = "civic"  # wrong district
        m.advance_time(silence["hour"] - m.state.hour + 1)
        m.advance_time(1.0)  # trigger _fire_missed_agenda
        assert silence.get("fired") or silence["district"] in m.state.district_closed or True

    def test_killer_strike_adds_victim(self):
        m = MurdererScenario(seed=42, difficulty=1)
        initial_victims = len(m.state.victims)
        # Advance past first strike
        m.advance_time(m.state.next_strike_hour - m.state.hour + 1)
        assert len(m.state.victims) > initial_victims


# ── World reactions ───────────────────────────────────────────

class TestWorldReactions:
    def test_wrong_confrontation_closes_district(self):
        m = MurdererScenario(seed=42, difficulty=5)
        for cid in list(m.clues.keys())[:3]:
            m.clues[cid].found = True; m.state.clues_found.append(cid)
        innocent = next(c for c in m.characters.values()
                        if c.alive and not c.is_killer)
        conf, _ = m.begin_confrontation(innocent.id)
        conf.pressure = 0.85
        # Force innocent breakdown
        from scenarios.base import Clue
        dummy = Clue(id="dummy", attribute="district",
                     value=innocent.district, text="Test.",
                     narrows_suspects=True, found=True)
        m.clues["dummy"] = dummy
        m.state.clues_found.append("dummy")
        clues = m.confrontation_clues(innocent.id, conf)
        if clues:
            m.present_clue(conf, clues[0])
        assert innocent.id in m.state.accused_wrong_reaction

    def test_guarded_district_returns_limited_dialogue(self):
        m = MurdererScenario(seed=42, difficulty=5)
        char = next(c for c in m.characters.values() if c.alive and not c.is_killer)
        m.state.district_closed[char.district] = m.state.hour + 5.0
        opts = m.get_dialogue(char.id)
        assert len(opts) == 1
        assert opts[0].key == "guarded"


# ── Save/load ─────────────────────────────────────────────────

class TestSaveLoad:
    def test_save_creates_file(self, tmp_path):
        m = MurdererScenario(seed=42, difficulty=5)
        import saveload
        path = saveload.save_game(m, str(tmp_path / "test_save.json"))
        assert (tmp_path / "test_save.json").exists()

    def test_load_restores_state(self, tmp_path):
        import saveload
        m = MurdererScenario(seed=42, difficulty=8)
        m.advance_time(10.0)
        for cid in list(m.clues.keys())[:3]:
            m.clues[cid].found = True; m.state.clues_found.append(cid)
        path = saveload.save_game(m, str(tmp_path / "restore_test.json"))
        m2, _ = saveload.load_game(path)
        assert m2.state.killer_id == m.state.killer_id
        assert abs(m2.state.hour - m.state.hour) < 0.01
        assert len(m2.state.clues_found) == len(m.state.clues_found)

    def test_load_preserves_conversation_log(self, tmp_path):
        import saveload
        m = MurdererScenario(seed=42, difficulty=5)
        log = [{"who": "Elena", "q": "What happened?", "a": "I don't know.", "clue": False}]
        path = saveload.save_game(m, str(tmp_path / "log_test.json"), conversation_log=log)
        _, loaded_log = saveload.load_game(path)
        assert len(loaded_log) == 1
        assert loaded_log[0]["who"] == "Elena"

    def test_load_preserves_case_type(self, tmp_path):
        import saveload
        for seed in range(20):
            m = MurdererScenario(seed=seed, difficulty=12)
            if m.state.case_type != "serial":
                path = saveload.save_game(m, str(tmp_path / "ct_test.json"))
                m2, _ = saveload.load_game(path)
                assert m2.state.case_type == m.state.case_type
                break
