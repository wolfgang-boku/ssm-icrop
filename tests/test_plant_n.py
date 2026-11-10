"""Tests for the plant N module.

The two nitrogen=2 reference scenarios verify PlantN against the reference
output in test_verification.py, over the whole season but for wheat only.
These tests call step_plant_n on hand-set crop state and cover what wheat
does not run: N fixation (bdBNF < 999), negative uptake, SGR = 0 and DDMP = 0
during seed growth, uptake in excess of grain demand and the FXLF limits.
They also check the plant N balance that the VBA's flows keep.
"""

import pytest

from ssm_icrop.plant_n import (
    SEASON_CARRY_FIELDS,
    PlantNParams,
    _allocate_to_leaf_and_stem,
    step_plant_n,
)
from ssm_icrop.state import SimState

GCC = 1.0


def make_params(**overrides) -> PlantNParams:
    values = dict(slng=1.5, slns=0.4, sncg=0.015, sncs1=0.0063, sncs2=0.0022,
                  gnc_min=0.016, gnc_max=0.042, mxnup=0.5)
    values.update(overrides)
    return PlantNParams(**values)


def make_state(**overrides) -> SimState:
    """A wheat crop after initialisation, in its vegetative phase."""
    state = SimState()
    state.ini_pnb = 1
    state.cbd_emr, state.cbd_bsg, state.cbd_tsg = 5.0, 50.0, 80.0
    state.cbd_bnf = 999.0
    state.cbd, state.bd = 20.0, 1.0
    state.lai, state.glai, state.gst = 1.0, 0.05, 5.0
    state.wst, state.wveg = 100.0, 150.0
    state.nst, state.nlf = 1.5, 1.5
    state.ddmp, state.sgr = 10.0, 0.0
    state.snavl, state.ftswrz = 5.0, 0.8
    for name, value in overrides.items():
        assert hasattr(state, name), name
        setattr(state, name, value)
    return state


def plant_n(state: SimState) -> float:
    return state.nlf + state.nst + state.ngrn


class TestInitialisation:
    def test_pools_start_at_growth_concentrations(self):
        """iCrop.vba:1428-1430, on the first call of the season."""
        state = make_state(ini_pnb=0, cbd=1.0, wst=0.5, lai=0.0, nst=9.0, nlf=9.0,
                           ngrn=9.0, bnf=0.3, cumbnf=2.0, wsfn=0.2)
        step_plant_n(state, make_params(), GCC)
        assert state.nst == 0.5 * 0.015
        assert state.nlf == 0.0
        assert state.cnup == state.nst + state.nlf
        assert (state.ngrn, state.bnf, state.cumbnf) == (0.0, 0.0, 0.0)
        assert state.wsfn == 1.0
        assert state.ini_pnb == 1

    def test_nfc_is_not_reset(self):
        """NFC is a running mean that neither iniPNB nor LocManagInputs resets
        (:1444), so it carries into the next season."""
        state = make_state(ini_pnb=0, nfc=0.04)
        step_plant_n(state, make_params(), GCC)
        assert state.nfc == pytest.approx(0.04 * 3 / 4 + state.nup / 150.0 / 4)
        assert "nfc" in SEASON_CARRY_FIELDS


class TestSncs:
    @pytest.mark.parametrize("cbd,expected", [(49.9, 0.0063), (50.0, 0.0022)])
    def test_switches_at_bsg(self, cbd, expected):
        """SNCS1 before bdBSG, SNCS2 from it on (:1433)."""
        state = make_state(cbd=cbd)
        step_plant_n(state, make_params(), GCC)
        assert state.sncs == expected


class TestNoUptakePhase:
    @pytest.mark.parametrize("cbd", [5.0, 80.1])
    def test_no_uptake_and_no_flows(self, cbd):
        """CBD <= bdEMR or CBD > bdTSG (:1435-1436)."""
        state = make_state(cbd=cbd, inlf=1.0, xnlf=1.0, ingrn=1.0)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.0
        assert (state.inlf, state.inst, state.xnlf, state.xnst, state.ingrn) == (0,) * 5
        assert (state.nst, state.nlf) == (1.5, 1.5)
        assert state.nstrs == 0.0

    def test_bnf_keeps_its_last_value(self):
        """BNF is not reset here, and CUMBNF does not grow (:1435-1436)."""
        state = make_state(cbd=80.1, bnf=0.3, cumbnf=2.0)
        step_plant_n(state, make_params(), GCC)
        assert (state.bnf, state.cumbnf) == (0.3, 2.0)


class TestVegetativeUptake:
    def test_demand_of_new_growth_plus_stem_deficit(self):
        """NUP = GST*SNCG + GLAI*SLNG + (WST*SNCG - NST) (:1439-1441)."""
        state = make_state()
        step_plant_n(state, make_params(), GCC)
        demand = 5.0 * 0.015 + 0.05 * 1.5 + 0.0  # NST 1.5 = WST*SNCG, no deficit
        assert state.nup == pytest.approx(demand)
        assert state.nstrs == pytest.approx(1.0)

    def test_capped_by_mxnup_then_by_snavl(self):
        """:1443 and, for a non-legume, :1449. NSTRS is NUP / potential NUP."""
        state = make_state(nst=0.0, snavl=0.2)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.2
        potential = 5.0 * 0.015 + 0.05 * 1.5 + 100.0 * 0.015
        assert state.nstrs == pytest.approx(0.2 / potential)

    def test_waterlogging_reduces_uptake(self):
        """FTSWRZ > 1: NUP * WSXF, with yesterday's WSXF (:1447)."""
        state = make_state(ftswrz=1.2, wsxf=0.5)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == pytest.approx(0.5 * (0.075 + 0.075))

    def test_no_uptake_without_dm_production(self):
        """DDMP = 0 (:1448)."""
        state = make_state(ddmp=0.0)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.0

    def test_negative_demand_is_zeroed(self):
        """NUP < 0 (:1446), from a negative stem growth."""
        state = make_state(gst=-20.0, glai=0.0)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.0

    def test_nfc_uses_the_capped_uptake(self):
        """NFC = NFC*3/4 + NUP/WVEG/4 after the MXNUP cap, before WSFN and the
        SNAVL cap (:1443-1444)."""
        state = make_state(nst=0.0, snavl=0.1, nfc=0.01)
        step_plant_n(state, make_params(), GCC)
        assert state.nfc == pytest.approx(0.01 * 0.75 + 0.5 / 150.0 * 0.25)


class TestVegetativeFixation:
    """Legume: bdBNF below bdBSG (iCrop.vba:1445-1453)."""

    def test_before_bnf_uptake_capped_at_snavl(self):
        state = make_state(cbd_bnf=30.0, snavl=0.1)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.1
        assert state.bnf == 0.0

    def test_after_bnf_uptake_beyond_snavl_is_fixed(self):
        state = make_state(cbd_bnf=10.0, snavl=0.1, wsfn=0.8)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == pytest.approx(0.15 * 0.8)
        assert state.bnf == pytest.approx(0.15 * 0.8 - 0.1)
        assert state.cumbnf == state.bnf

    def test_bnf_keeps_yesterdays_value_when_soil_suffices(self):
        """VBA behaviour kept: BNF is assigned only when NUP > SNAVL (:1451),
        so on a day the soil covers the uptake yesterday's BNF stays and
        CUMBNF adds it again."""
        state = make_state(cbd_bnf=10.0, snavl=5.0, bnf=0.3, cumbnf=1.0)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == pytest.approx(0.15)
        assert state.bnf == 0.3
        assert state.cumbnf == pytest.approx(1.3)


class TestAllocation:
    """_allocate_to_leaf_and_stem (iCrop.vba:1455-1479); returns
    (INST, XNST, INLF, XNLF). Floor: WST * SNCS = 100 * 0.005 = 0.5."""

    @pytest.mark.parametrize(
        "nst,supply,expected",
        [
            (0.2, 0.1, (0.3, 0.0, 0.0, 0.2)),    # stem deficit > supply: leaf N to stem
            (0.2, 0.4, (0.325, 0.0, 0.075, 0.0)),  # leaf gets GLAI*SLNG, stem the rest
            (0.2, 0.33, (0.3, 0.0, 0.03, 0.0)),  # leaf gets only what remains
            (0.6, 0.05, (0.0, 0.025, 0.075, 0.0)),  # leaf short: stem N to leaf
            (0.51, 0.05, (0.0, 0.01, 0.06, 0.0)),   # ... limited to NST - floor
            (0.6, 0.2, (0.125, 0.0, 0.075, 0.0)),   # leaf filled, rest to stem
        ],
    )
    def test_cases(self, nst, supply, expected):
        state = make_state(nst=nst, wst=100.0, sncs=0.005, glai=0.05)
        assert _allocate_to_leaf_and_stem(state, make_params(), supply) == (
            pytest.approx(expected)
        )

    @pytest.mark.parametrize("nst,supply", [(0.2, 0.1), (0.2, 0.4), (0.6, 0.05),
                                            (0.51, 0.05), (0.6, 0.2)])
    def test_net_gain_equals_supply(self, nst, supply):
        state = make_state(nst=nst, wst=100.0, sncs=0.005, glai=0.05)
        inst, xnst, inlf, xnlf = _allocate_to_leaf_and_stem(state, make_params(), supply)
        assert inst - xnst + inlf - xnlf == pytest.approx(supply)


def seed_state(**overrides) -> SimState:
    """Seed growth: BSG <= CBD <= TSG, SGR 10 g m-2 d-1."""
    values = dict(cbd=60.0, sgr=10.0, ddmp=12.0, glai=0.0, gst=0.0,
                  trln=2.0, fxlf=0.6, snavl=5.0)
    values.update(overrides)
    return make_state(**values)


class TestSeedGrowth:
    def test_uptake_for_grain_at_gnc_max(self):
        """INGRN = SGR*GNCmax as first estimate (:1483-1484)."""
        state = seed_state()
        step_plant_n(state, make_params(), GCC)
        assert state.nup == pytest.approx(10.0 * 0.042)

    def test_grain_n_capped_at_gnc_max(self):
        """Translocation from TRLN would exceed SGR*GNCmax (:1516-1518)."""
        state = seed_state()
        step_plant_n(state, make_params(), GCC)
        assert state.ingrn == pytest.approx(10.0 * 0.042)

    def test_grain_n_raised_to_gnc_min_by_translocation(self):
        """INGRN < SGR*GNCmin; the gap comes from leaf and stem in the ratio
        FXLF : 1 - FXLF (:1513-1514, :1550-1555)."""
        state = seed_state(snavl=0.0, trln=0.0)
        nlf, nst = state.nlf, state.nst
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.0
        assert state.ingrn == pytest.approx(10.0 * 0.016)
        assert nlf - state.nlf == pytest.approx(0.16 * 0.6)
        assert nst - state.nst == pytest.approx(0.16 * 0.4)

    def test_no_uptake_when_grain_draws_on_reserves(self):
        """DDMP < SGR/GCC: grain growth uses translocated DM, NUP = 0 (:1501)."""
        state = seed_state(ddmp=8.0)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.0

    def test_no_supply_from_vegetation_without_seed_growth(self):
        """SGR = 0: XNVEG = 0 (:1510), and grain gets no N."""
        state = seed_state(sgr=0.0, glai=0.05)
        step_plant_n(state, make_params(), GCC)
        assert state.ingrn == 0.0
        assert state.nup == pytest.approx(0.075)

    def test_no_uptake_without_dm_production(self):
        """DDMP = 0 with SGR = 0 (:1502); DDMP < SGR/GCC does not catch it."""
        state = seed_state(sgr=0.0, ddmp=0.0, glai=0.05)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == 0.0

    def test_uptake_beyond_grain_demand_goes_to_leaf_and_stem(self):
        """NUP > INGRN: NUP2 = NUP - INGRN is allocated like vegetative uptake
        (:1521-1548)."""
        state = seed_state(sgr=1.0, glai=0.05, gst=5.0, trln=0.0, nst=2.0)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == pytest.approx(0.042 + 0.075 + 0.075)
        assert state.ingrn == pytest.approx(0.042)
        assert state.inlf == pytest.approx(0.075)
        assert state.inst == pytest.approx(0.075)

    def test_waterlogging_reduces_uptake(self):
        """FTSWRZ > 1: NUP * WSXF (:1500)."""
        state = seed_state(ftswrz=1.5, wsxf=0.5)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == pytest.approx(0.21)


class TestSeedGrowthFixation:
    """Legume past bdBNF (iCrop.vba:1490-1507)."""

    def test_fixation_lifts_the_snavl_cap(self):
        """DNF = min(NFC*WVEG, NUP) * WSFN; NUP <= SNAVL + DNF; BNF = NUP - SNAVL."""
        state = seed_state(cbd_bnf=10.0, snavl=0.1, nfc=0.001, wsfn=0.5)
        step_plant_n(state, make_params(), GCC)
        dnf = 0.001 * 150.0 * 0.5
        assert state.nup == pytest.approx(0.1 + dnf)
        assert state.bnf == pytest.approx(dnf)
        assert state.cumbnf == pytest.approx(dnf)

    def test_no_fixation_when_ddmp_does_not_exceed_grain_cost(self):
        """DDMP <= SGR/GCC: DNF = 0 (:1496), at equality too, where NUP is not
        zeroed (:1501 has <)."""
        state = seed_state(cbd_bnf=10.0, snavl=0.1, nfc=0.001, ddmp=10.0)
        step_plant_n(state, make_params(), GCC)
        assert state.nup == pytest.approx(0.1)
        assert state.bnf == 0.0

    def test_bnf_is_assigned_every_day(self):
        """Unlike before bdBSG, BNF = NUP - SNAVL is set each day (:1505-1506)."""
        state = seed_state(cbd_bnf=10.0, snavl=5.0, bnf=0.3)
        step_plant_n(state, make_params(), GCC)
        assert state.bnf == 0.0


class TestEndOfDay:
    @pytest.mark.parametrize("phase", [dict(cbd=20.0), dict(cbd=60.0, sgr=10.0),
                                       dict(cbd=60.0, sgr=10.0, snavl=0.0),
                                       dict(cbd=60.0, sgr=1.0, gst=5.0, glai=0.05)])
    def test_plant_n_grows_by_nup(self, phase):
        """The flows conserve N: leaf + stem + grain N grows by NUP (:1559-1563)."""
        state = make_state(trln=2.0, fxlf=0.6, **phase)
        before = plant_n(state)
        step_plant_n(state, make_params(), GCC)
        assert plant_n(state) - before == pytest.approx(state.nup)

    def test_translocatable_n(self):
        """TRLN = LAI*(SLNG-SLNS) + NST - WST*SNCS; FXLF its leaf share (:1565-1566)."""
        state = make_state(cbd=85.0, lai=1.0, nst=1.0, wst=100.0)
        step_plant_n(state, make_params(), GCC)
        assert state.trln == pytest.approx(1.1 + 1.0 - 0.22)
        assert state.fxlf == pytest.approx(1.1 / 1.88)

    @pytest.mark.parametrize("nst,expected", [(0.1, 1.0), (-2.0, 0.0)])
    def test_fxlf_limits(self, nst, expected):
        """FXLF is limited to 0..1 (:1567-1568): TRLN < LAI*(SLNG-SLNS) gives
        FXLF > 1, a negative TRLN a negative FXLF."""
        state = make_state(cbd=85.0, lai=1.0, nst=nst, wst=100.0)
        step_plant_n(state, make_params(), GCC)
        assert state.fxlf == expected
