"""Tests for the crop LAI module."""

import pytest

from ssm_icrop.crop_lai import LAIParams, step_lai
from ssm_icrop.state import SimState


def make_params(**overrides) -> LAIParams:
    defaults = dict(
        phyl=45.0,
        placon=0.6,
        plapow=1.5,
        a_pla_den=1.0,
        b_pla_den=0.0,
        sla=0.022,
        frztkil=-4.0,
        frzldr=0.1,
        htlth=34.0,
        htldr=0.05,
    )
    defaults.update(overrides)
    return LAIParams(**defaults)


def make_state(**overrides) -> SimState:
    state = SimState()
    state.ini_lai = 1  # skip re-initialization; most tests exercise a mid-season day
    state.cbd_blg = 8.0
    state.cbd_tlm = 60.0
    state.cbd_tlp = 100.0
    state.cbd_bls = 100.0
    state.cbd_bsg = 100.0
    state.cbd_tsg = 130.0
    state.cbd_mat = 155.0
    state.dtu = 15.0
    state.bd = 1.0
    state.tmin = 10.0
    state.tmax = 25.0
    state.wsfl = 1.0
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


class TestInitialization:
    def test_first_call_sets_flags(self):
        params = make_params()
        state = make_state(cbd=20.0, ini_lai=0)
        step_lai(state, params, pden=250.0)

        assert state.ini_lai == 1
        assert state.msnn >= 1.0
        assert state.mxlai >= 0.0

    def test_init_only_runs_once(self):
        params = make_params()
        state = make_state(cbd=20.0, ini_lai=0)
        step_lai(state, params, pden=250.0)
        state.msnn = 99.0  # sentinel — should not be reset on second call
        step_lai(state, params, pden=250.0)
        assert state.msnn != 1.0


class TestGrowthPhase:
    def test_no_growth_before_blg(self):
        params = make_params()
        state = make_state(cbd=5.0)  # before cbd_blg=8
        step_lai(state, params, pden=250.0)
        assert state.glai == 0.0

    def test_growth_in_node_phase(self):
        """cbd_blg < cbd <= cbd_tlm: leaf area grows via node-based PLACON/PLAPOW."""
        params = make_params()
        state = make_state(cbd=20.0)
        initial_msnn = state.msnn
        step_lai(state, params, pden=250.0)

        assert state.msnn > initial_msnn
        assert state.glai > 0.0
        assert state.pla1 > 0.0

    def test_pla2_updated_alongside_pla1(self):
        """Regression test: state.pla2 was computed locally but never written back."""
        params = make_params()
        state = make_state(cbd=20.0)
        step_lai(state, params, pden=250.0)

        assert state.pla2 == pytest.approx(state.pla1)
        assert state.pla2 > 0.0

    def test_growth_in_glf_phase(self):
        """cbd_tlm < cbd <= cbd_tlp: leaf area grows via GLF * SLA."""
        params = make_params()
        state = make_state(cbd=80.0, glf=5.0)
        step_lai(state, params, pden=250.0)

        assert state.glai == pytest.approx(5.0 * params.sla)

    def test_no_growth_after_tlp(self):
        params = make_params()
        state = make_state(cbd=120.0)
        step_lai(state, params, pden=250.0)
        assert state.glai == 0.0


class TestSenescence:
    def test_no_senescence_before_bls(self):
        params = make_params()
        state = make_state(cbd=50.0, lai=2.0)
        step_lai(state, params, pden=250.0)
        assert state.dlai == 0.0
        assert state.blslai == pytest.approx(state.lai)

    def test_senescence_after_bls(self):
        params = make_params()
        state = make_state(cbd=110.0, blslai=3.0, bd=1.0)
        step_lai(state, params, pden=250.0)
        expected = 1.0 / (155.0 - 100.0) * 3.0
        assert state.dlai == pytest.approx(expected)


class TestFrostHeat:
    def test_frost_increases_dlai(self):
        params = make_params(frztkil=-2.0, frzldr=0.2)
        state = make_state(cbd=110.0, blslai=1.0, bd=0.1, tmin=-6.0, lai=2.0)
        step_lai(state, params, pden=250.0)

        # frstf = |(-6) - (-2)| * 0.2 = 0.8; dlaif = lai * frstf = 2.0*0.8=1.6
        base_dlai = 0.1 / (155.0 - 100.0) * 1.0
        assert state.dlai > base_dlai
        assert state.dlai == pytest.approx(2.0 * 0.8)

    def test_no_frost_before_blg(self):
        params = make_params(frztkil=-2.0, frzldr=0.2)
        state = make_state(cbd=5.0, tmin=-20.0, lai=2.0)
        step_lai(state, params, pden=250.0)
        assert state.dlai == 0.0

    def test_heat_amplifies_existing_dlai(self):
        params = make_params(htlth=30.0, htldr=0.1)
        state = make_state(cbd=110.0, blslai=2.0, bd=1.0, tmax=40.0)
        step_lai(state, params, pden=250.0)

        base_dlai = 1.0 / (155.0 - 100.0) * 2.0
        heatf = 1.0 + (40.0 - 30.0) * 0.1  # = 2.0
        assert state.dlai == pytest.approx(base_dlai * heatf)

    def test_heat_has_no_effect_when_dlai_is_zero(self):
        """Matches VBA: heat only amplifies an already-nonzero DLAI."""
        params = make_params(htlth=30.0, htldr=0.5)
        state = make_state(cbd=50.0, tmax=40.0)  # before bls, dlai starts at 0
        step_lai(state, params, pden=250.0)
        assert state.dlai == 0.0


class TestPrematureMaturity:
    def test_low_lai_during_grain_fill_triggers_premature_maturity(self):
        params = make_params()
        state = make_state(cbd=110.0, lai=0.0, glai=0.0, dlai=0.0)
        step_lai(state, params, pden=250.0)

        assert state.cbd == state.cbd_tsg
        assert state.matyp == 2

    def test_healthy_lai_does_not_trigger_maturity(self):
        params = make_params()
        state = make_state(cbd=110.0, lai=2.0, glai=0.0, dlai=0.0)
        step_lai(state, params, pden=250.0)

        assert state.matyp != 2


class TestLAIUpdate:
    def test_lai_accumulates_growth_and_death(self):
        params = make_params()
        state = make_state(cbd=50.0, lai=2.0, glai=0.5, dlai=0.2)
        step_lai(state, params, pden=250.0)
        # LAI is updated at the top of the function using yesterday's glai/dlai
        assert state.mxlai >= 2.3

    def test_lai_clamped_at_zero(self):
        params = make_params()
        state = make_state(cbd=50.0, lai=0.1, glai=0.0, dlai=5.0)
        step_lai(state, params, pden=250.0)
        assert state.lai >= 0.0

    def test_mxlai_tracks_maximum(self):
        params = make_params()
        state = make_state(cbd=50.0, lai=3.0, glai=0.0, dlai=0.0, mxlai=1.0)
        step_lai(state, params, pden=250.0)
        assert state.mxlai == pytest.approx(3.0)
