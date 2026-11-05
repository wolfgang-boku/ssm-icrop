"""Tests for phenology module."""

import pytest

from ssm_icrop.phenology import (
    LegumeParams,
    MaizeParams,
    WheatParams,
    _photoperiod_response,
    _solar_geometry,
    _temperature_response_beta,
    _temperature_response_dent,
    _temperature_response_dent_maize,
    step_phenology,
)
from ssm_icrop.state import SimState


class TestTemperatureResponse:
    """Test cardinal temperature functions."""

    def test_wheat_beta_below_base(self):
        result = _temperature_response_beta(0.0, 2.0, 15.0, 25.0, 33.0)
        assert result == 0.0

    def test_wheat_beta_optimal(self):
        result = _temperature_response_beta(20.0, 2.0, 15.0, 25.0, 33.0)
        assert result > 0.0

    def test_wheat_beta_above_ceiling(self):
        result = _temperature_response_beta(35.0, 2.0, 15.0, 25.0, 33.0)
        assert result == 0.0

    def test_dent_below_base(self):
        result = _temperature_response_dent(8.0, 10.0, 25.0, 30.0, 40.0)
        assert result == 0.0

    def test_dent_rising_phase(self):
        result = _temperature_response_dent(15.0, 10.0, 25.0, 30.0, 40.0)
        assert result > 0.0
        assert result < 1.0

    def test_dent_optimal(self):
        result = _temperature_response_dent(27.0, 10.0, 25.0, 30.0, 40.0)
        assert result == 1.0

    def test_dent_maize_replicates_vba_tp2_bug(self):
        """iCrop.vba:455 divides by TCD instead of (TCD-TP2D) in the falling
        branch -- confirm the maize-specific function matches VBA's actual
        (buggy) output, not the mathematically 'correct' shared dent fn."""
        tbd, tp1d, tp2d, tcd = 8.0, 30.0, 34.0, 44.0
        tmp = 40.0  # in the TP2D < tmp < TCD band

        vba_result = _temperature_response_dent_maize(tmp, tbd, tp1d, tp2d, tcd)
        corrected_result = _temperature_response_dent(tmp, tbd, tp1d, tp2d, tcd)

        assert vba_result == pytest.approx((tcd - tmp) / tcd)
        assert vba_result != pytest.approx(corrected_result)

    def test_dent_maize_matches_shared_dent_outside_falling_branch(self):
        """The TP2 bug only affects the TP2D<tmp<TCD band; other bands agree
        with the shared (correct) dent function."""
        tbd, tp1d, tp2d, tcd = 8.0, 30.0, 34.0, 44.0

        for tmp in [5.0, 15.0, 32.0]:  # below base, rising phase, plateau
            maize_result = _temperature_response_dent_maize(tmp, tbd, tp1d, tp2d, tcd)
            shared_result = _temperature_response_dent(tmp, tbd, tp1d, tp2d, tcd)
            assert maize_result == pytest.approx(shared_result)


class TestPhotoperiodResponse:
    """Test photoperiod response."""

    def test_outside_sensitive_period(self):
        # Outside the sensitive period, should return 1.0
        dayl, _, _, _ = _solar_geometry(doy=100, lat=40.0)
        result = _photoperiod_response(
            pp=dayl + 0.9, cpp=12.0, ppsen=0.0,
            cbd=0.0, cbd_brp=10.0, cbd_trp=30.0,
            crop_type="WHEAT"
        )
        assert result == 1.0

    def test_wheat_short_day_sensitivity(self):
        # Inside sensitive period, short days (< cpp)
        dayl, _, _, _ = _solar_geometry(doy=50, lat=50.0)
        result = _photoperiod_response(
            pp=dayl + 0.9, cpp=12.0, ppsen=0.01,
            cbd=20.0, cbd_brp=10.0, cbd_trp=50.0,
            crop_type="WHEAT"
        )
        # High latitude in early season = short day, should reduce development
        assert 0.0 <= result <= 1.0

    def test_wheat_no_upper_clamp_matches_vba(self):
        """VBA only clamps ppfun's lower bound; negative ppsen can push it >1."""
        dayl, _, _, _ = _solar_geometry(doy=50, lat=50.0)
        pp = dayl + 0.9
        result = _photoperiod_response(
            pp=pp, cpp=12.0, ppsen=-0.05,  # negative sensitivity
            cbd=20.0, cbd_brp=10.0, cbd_trp=50.0,
            crop_type="WHEAT"
        )
        assert result > 1.0


class TestWheatPhenology:
    """Test wheat phenology progression."""

    def test_wheat_initialization(self):
        params = WheatParams(
            tbd=0.0, tp1d=15.0, tp2d=25.0, tcd=33.0,
            vdsat=50.0, vsen=0.0,
            cpp=12.0, ppsen=0.0,
            bd_sowemr=5.0, bd_emrtil=10.0, bd_tilsel=15.0,
            bd_selbot=10.0, bd_botear=8.0, bd_earant=7.0,
            bd_antpm=30.0, bd_pmhm=10.0,
        )
        state = SimState()
        state.tmp = 15.0
        state.doy = 100
        state.lat = 38.0

        step_phenology(state, params, "WHEAT", lat=38.0)

        assert state.ini_pheno == 1
        assert state.cbd_emr == 5.0
        assert state.dtu > 0.0
        assert state.cbd > 0.0
        assert state.dap == 1

    def test_wheat_stage_transitions(self):
        """Test that stage dates are recorded correctly."""
        params = WheatParams(
            tbd=0.0, tp1d=15.0, tp2d=25.0, tcd=33.0,
            vdsat=50.0, vsen=0.0,
            cpp=12.0, ppsen=0.0,
            bd_sowemr=1.0, bd_emrtil=5.0, bd_tilsel=10.0,
            bd_selbot=5.0, bd_botear=5.0, bd_earant=5.0,
            bd_antpm=15.0, bd_pmhm=5.0,
        )
        state = SimState()
        state.tmp = 18.0
        state.doy = 100
        state.wsfg = 1.0

        # Run until emergence
        for i in range(50):
            step_phenology(state, params, "WHEAT", lat=38.0)
            if state.cbd >= state.cbd_emr:
                assert state.dt_emr > 0
                break

    def test_wheat_maturity(self):
        """Test that maturity is reached."""
        params = WheatParams(
            tbd=0.0, tp1d=20.0, tp2d=25.0, tcd=33.0,
            vdsat=0.0, vsen=0.0,  # no vernalization needed
            cpp=12.0, ppsen=0.0,
            bd_sowemr=1.0, bd_emrtil=5.0, bd_tilsel=5.0,
            bd_selbot=5.0, bd_botear=5.0, bd_earant=5.0,
            bd_antpm=10.0, bd_pmhm=3.0,
        )
        state = SimState()
        state.tmp = 20.0
        state.doy = 100
        state.wsfg = 1.0

        # Run until maturity
        for i in range(1000):
            step_phenology(state, params, "WHEAT", lat=38.0)
            if state.mat == 1:
                assert state.matyp == 1
                return

        pytest.fail("Wheat did not reach maturity within 1000 days")

    def test_maturity_boundary_is_strict_greater_than(self):
        """VBA: `If CBD > bdMAT` — reaching cbd_mat exactly must NOT trigger MAT=1.

        Freeze cbd exactly at cbd_mat by forcing bd=0 (tmp outside the
        cardinal range, so tempfun=0), then confirm the real maturity check
        doesn't fire on equality — only strictly exceeding it should.
        """
        params = WheatParams(
            tbd=0.0, tp1d=20.0, tp2d=25.0, tcd=33.0,
            vdsat=0.0, vsen=0.0,
            cpp=12.0, ppsen=0.0,
            bd_sowemr=1.0, bd_emrtil=5.0, bd_tilsel=5.0,
            bd_selbot=5.0, bd_botear=5.0, bd_earant=5.0,
            bd_antpm=10.0, bd_pmhm=3.0,
        )
        state = SimState()
        state.tmp = 20.0
        state.doy = 100
        state.wsfg = 1.0
        step_phenology(state, params, "WHEAT", lat=38.0)  # init

        state.cbd = state.cbd_mat  # land exactly on the threshold
        state.tmp = 100.0  # outside cardinal range -> tempfun=0 -> bd=0, cbd frozen
        step_phenology(state, params, "WHEAT", lat=38.0)

        assert state.cbd == pytest.approx(state.cbd_mat)  # cbd didn't move
        assert state.mat == 0  # exact equality must not trigger maturity

        # One more day with bd>0 pushes cbd strictly past cbd_mat -> maturity fires
        state.tmp = 20.0
        step_phenology(state, params, "WHEAT", lat=38.0)
        assert state.cbd > state.cbd_mat
        assert state.mat == 1
        assert state.matyp == 1

    def test_wsfd_distinct_from_wsfg(self):
        """WSFD (drought-acceleration), not WSFG, must scale post-emergence bd/dtu."""
        import copy

        params = WheatParams(
            tbd=0.0, tp1d=20.0, tp2d=25.0, tcd=33.0,
            vdsat=0.0, vsen=0.0,
            cpp=12.0, ppsen=0.0,
            bd_sowemr=1.0, bd_emrtil=5.0, bd_tilsel=5.0,
            bd_selbot=5.0, bd_botear=5.0, bd_earant=5.0,
            bd_antpm=10.0, bd_pmhm=3.0,
        )
        # Advance a clean state past emergence first
        emerged = SimState()
        emerged.tmp = 20.0
        emerged.doy = 100
        for _ in range(5):
            step_phenology(emerged, params, "WHEAT", lat=38.0)
            if emerged.cbd > emerged.cbd_emr:
                break
        assert emerged.cbd > emerged.cbd_emr

        # Branch A: RUE-only stress (wsfg low), development unaffected (wsfd=1)
        rue_stressed = copy.deepcopy(emerged)
        rue_stressed.wsfg = 0.3
        rue_stressed.wsfd = 1.0
        cbd_before_a = rue_stressed.cbd
        step_phenology(rue_stressed, params, "WHEAT", lat=38.0)
        bd_gained_a = rue_stressed.cbd - cbd_before_a

        # Branch B: no RUE stress, but development stress applied via wsfd
        dev_stressed = copy.deepcopy(emerged)
        dev_stressed.wsfg = 1.0
        dev_stressed.wsfd = 0.3
        cbd_before_b = dev_stressed.cbd
        step_phenology(dev_stressed, params, "WHEAT", lat=38.0)
        bd_gained_b = dev_stressed.cbd - cbd_before_b

        # If bd/dtu were (bug) scaled by wsfg instead of wsfd, branch A (low
        # wsfg) would show the SAME reduced gain as branch B (low wsfd).
        # With the fix, branch A's gain is unaffected by wsfg, so they differ.
        assert bd_gained_a != pytest.approx(bd_gained_b)
        assert bd_gained_b == pytest.approx(bd_gained_a * 0.3, rel=1e-6)


class TestMaizePhenology:
    """Test maize phenology progression."""

    def test_maize_initialization(self):
        params = MaizeParams(
            tbd=8.0, tp1d=34.0, tp2d=34.0, tcd=44.0,
            cpp=12.5, ppsen=0.0,
            bd_sowemr=6.0, bd_emreju=15.0, bd_silpm=35.0,
            phyl=45.0,
        )
        state = SimState()
        state.tmp = 25.0
        state.doy = 160
        state.wsfg = 1.0

        step_phenology(state, params, "MAIZE", lat=38.0)

        assert state.ini_pheno == 1
        assert state.cbd_emr == 6.0
        assert state.cbd_sil > state.cbd_tsi  # initial silking estimate set
        assert state.dap == 1

    def test_maize_tsi_recalculation(self):
        """Once CBD passes TSI, silking/downstream stages get recalculated."""
        params = MaizeParams(
            tbd=8.0, tp1d=34.0, tp2d=34.0, tcd=44.0,
            cpp=12.5, ppsen=0.0,
            bd_sowemr=1.0, bd_emreju=3.0, bd_silpm=10.0,
            phyl=20.0,
        )
        state = SimState()
        state.tmp = 30.0
        state.doy = 160
        state.wsfg = 1.0

        for _ in range(30):
            step_phenology(state, params, "MAIZE", lat=38.0)
            if state.xtsi == 1:
                break

        assert state.xtsi == 1
        assert state.cbd_tlm == state.cbd_sil
        assert state.cbd_bls == state.cbd_bsg

    def test_maize_maturity(self):
        params = MaizeParams(
            tbd=8.0, tp1d=34.0, tp2d=34.0, tcd=44.0,
            cpp=12.5, ppsen=0.0,
            bd_sowemr=1.0, bd_emreju=3.0, bd_silpm=10.0,
            phyl=20.0,
        )
        state = SimState()
        state.tmp = 28.0
        state.doy = 160
        state.wsfg = 1.0

        for _ in range(300):
            step_phenology(state, params, "MAIZE", lat=38.0)
            if state.mat == 1:
                assert state.matyp == 1
                return

        pytest.fail("Maize did not reach maturity within 300 days")

    def test_maize_not_applicable_stages_get_sentinel(self):
        """VBA sets dtR2=dtR3=dtR4=dtR5=dtR6=-9 for maize (stages don't apply)."""
        params = MaizeParams(
            tbd=8.0, tp1d=34.0, tp2d=34.0, tcd=44.0,
            cpp=12.5, ppsen=0.0,
            bd_sowemr=6.0, bd_emreju=15.0, bd_silpm=35.0,
            phyl=45.0,
        )
        state = SimState()
        state.tmp = 25.0
        state.doy = 160
        state.wsfg = 1.0

        step_phenology(state, params, "MAIZE", lat=38.0)

        assert state.dt_r2 == -9
        assert state.dt_r3 == -9
        assert state.dt_r4 == -9
        assert state.dt_r5 == -9
        assert state.dt_r6 == -9

    def test_maize_tassel_emergence_tracked_as_dt_r0(self):
        """VBA sets dtR0=dtTSE (tassel emergence); the port must track cbd_tse."""
        params = MaizeParams(
            tbd=8.0, tp1d=34.0, tp2d=34.0, tcd=44.0,
            cpp=12.5, ppsen=0.0,
            bd_sowemr=1.0, bd_emreju=3.0, bd_silpm=10.0,
            phyl=20.0,
        )
        state = SimState()
        state.tmp = 30.0
        state.doy = 160
        state.wsfg = 1.0

        for _ in range(60):
            step_phenology(state, params, "MAIZE", lat=38.0)
            if state.cbd >= state.cbd_tse and state.dt_r0 != 0:
                break

        assert state.dt_r0 > 0
        assert state.dt_r0 != -9


class TestLegumePhenology:
    """Test legume phenology progression."""

    def test_legume_initialization(self):
        params = LegumeParams(
            tbd=5.0, tp1d=20.0, tp2d=25.0, tcd=35.0,
            cpp=12.5, ppsen=0.0,
            bd_sowemr=3.0, bd_emrr1=8.0, bd_r1r3=12.0,
            bd_r3r5=15.0, bd_r5r7=10.0, bd_r7r8=8.0,
            bd_brp=3.0, bd_trp=11.0, bd_bsg=30.0, bd_tsg=45.0,
            bd_tlm=25.0, bd_tlp=30.0, bd_bls=30.0,
        )
        state = SimState()
        state.tmp = 20.0
        state.doy = 150
        state.wsfg = 1.0

        step_phenology(state, params, "SOYBEAN", lat=40.0)

        assert state.ini_pheno == 1
        assert state.cbd_emr == 3.0
        assert state.cbd > 0.0
        assert state.dap == 1

        # bd_bsg/bd_tsg are explicit legume crop parameters, distinct from
        # the derived R-stage chain (unlike wheat/maize) — must be applied.
        assert state.cbd_bsg == 30.0
        assert state.cbd_tsg == 45.0

        # VBA sets dtR0=-9 for legumes (stage doesn't apply)
        assert state.dt_r0 == -9

    def test_legume_rue_window_is_populated(self):
        """Regression test: cbd_bsg/cbd_tsg=0.0 previously zeroed RUE for the
        whole season (dm_production's window is [cbd_emr, cbd_tsg])."""
        params = LegumeParams(
            tbd=5.0, tp1d=20.0, tp2d=25.0, tcd=35.0,
            cpp=12.5, ppsen=0.0,
            bd_sowemr=3.0, bd_emrr1=8.0, bd_r1r3=12.0,
            bd_r3r5=15.0, bd_r5r7=10.0, bd_r7r8=8.0,
            bd_brp=3.0, bd_trp=11.0, bd_bsg=30.0, bd_tsg=45.0,
            bd_tlm=25.0, bd_tlp=30.0, bd_bls=30.0,
        )
        state = SimState()
        state.tmp = 20.0
        state.doy = 150
        state.wsfg = 1.0

        for _ in range(10):
            step_phenology(state, params, "SOYBEAN", lat=40.0)

        # cbd_tsg must have grown well past 0.0 (the pre-fix default) so a
        # normally-developing crop stays inside the RUE window for a while.
        assert state.cbd_tsg > 10.0
        assert state.cbd < state.cbd_tsg


class TestInitialisationResets:
    """What each crop's init block resets on crop day 1, after Weather has run
    (wheat iCrop.vba:283, maize :440, legume :603)."""

    WHEAT = WheatParams(
        tbd=0.0, tp1d=15.0, tp2d=25.0, tcd=33.0, vdsat=50.0, vsen=0.0,
        cpp=12.0, ppsen=0.0, bd_sowemr=5.0, bd_emrtil=10.0, bd_tilsel=15.0,
        bd_selbot=10.0, bd_botear=8.0, bd_earant=7.0, bd_antpm=30.0, bd_pmhm=10.0,
    )
    MAIZE = MaizeParams(
        tbd=8.0, tp1d=34.0, tp2d=34.0, tcd=44.0, cpp=12.5, ppsen=0.0,
        bd_sowemr=6.0, bd_emreju=15.0, bd_silpm=35.0, phyl=45.0,
    )
    LEGUME = LegumeParams(
        tbd=5.0, tp1d=20.0, tp2d=25.0, tcd=35.0, cpp=12.5, ppsen=0.0,
        bd_sowemr=3.0, bd_emrr1=8.0, bd_r1r3=12.0, bd_r3r5=15.0, bd_r5r7=10.0,
        bd_r7r8=8.0, bd_brp=3.0, bd_trp=11.0, bd_bsg=30.0, bd_tsg=45.0,
        bd_tlm=25.0, bd_tlp=30.0, bd_bls=30.0,
    )

    def _day_one(self, params, crop_type):
        """Crop day 1 with leftovers: snow from today's Weather, a CBD and DAP
        a pre-sowing flood kill could leave, and SoilWater's FTSW(1)."""
        state = SimState()
        state.tmp, state.tmax, state.tmin, state.doy = 20.0, 25.0, 15.0, 150
        state.snow = 12.0
        state.cbd = 40.0
        state.dap = 7
        state.ftsw[0] = 0.2
        step_phenology(state, params, crop_type, lat=38.0)
        return state

    def test_wheat_drops_snow_and_sets_ftsw1(self):
        state = self._day_one(self.WHEAT, "WHEAT")
        assert state.snow == 0.0
        assert state.ftsw[0] == 0.5
        assert state.dap == 1
        assert state.cbd <= 1.0  # one day's increment (at most 1) on 0, not on 40

    def test_maize_keeps_snow_and_ftsw1(self):
        state = self._day_one(self.MAIZE, "MAIZE")
        assert state.snow == 12.0
        assert state.ftsw[0] == 0.2
        assert state.dap == 1
        assert state.cbd <= 1.0

    def test_legume_sets_ftsw1_but_keeps_snow(self):
        state = self._day_one(self.LEGUME, "SOYBEAN")
        assert state.snow == 12.0
        assert state.ftsw[0] == 0.5
        assert state.dap == 1
        assert state.cbd <= 1.0
