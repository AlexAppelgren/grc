"""The name an instrument goes by on screen (D-133): its short name when that is one to three
words, else the compact official reference, built only from what the reference says."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.library.short_names import shown_short_name

GOD_SKIK = "Bekendtgørelse om god skik for finansielle virksomheder"


class ShownShortNameTests(SimpleTestCase):
    def test_a_short_name_of_three_words_or_fewer_is_shown_as_it_is(self) -> None:
        for short_name in ("LVM", "FFFS 2017:2", "MiFID II", "MAR RTS 2016/958"):
            self.assertEqual(shown_short_name(short_name, "Anything at all, however long it runs"), short_name)

    def test_a_danish_reference_reads_kind_number_and_year(self) -> None:
        self.assertEqual(shown_short_name(GOD_SKIK, "BEK nr 330 af 07/04/2016"), "BEK 330/2016")
        self.assertEqual(shown_short_name("Lov om finansiel virksomhed", "LOV nr 453 af 10/06/2003"), "LOV 453/2003")

    def test_a_union_act_reads_the_union_and_its_number(self) -> None:
        long = "High-risk third countries Delegated Regulation"
        self.assertEqual(shown_short_name(long, "Commission Delegated Regulation (EU) 2016/167"), "EU 2016/167")
        self.assertEqual(shown_short_name(long, "Council Regulation (EU) No 833/2014"), "EU 833/2014")
        self.assertEqual(shown_short_name(long, "Council Regulation (EC) No 881/2002"), "EC 881/2002")
        self.assertEqual(shown_short_name(long, "Council Directive 2014/107/EU"), "EU 2014/107")
        self.assertEqual(shown_short_name("MiFID II delegated directive", "CELEX 32017L0593"), "EU 2017/593")

    def test_any_other_reference_short_enough_by_itself_is_shown_as_it_is(self) -> None:
        for reference in ("SFS 2023:677", "FOR-2019-02-15-152", "929/2021", "EBA/GL/2021/02", "ESMA34-671404336-1364"):
            self.assertEqual(shown_short_name("Lag om frysning av tillgångar", reference), reference)

    def test_a_reference_nothing_fits_leaves_the_short_name(self) -> None:
        long = "Rahanpesun ja terrorismin rahoittamisen estäminen"
        self.assertEqual(shown_short_name(long, "Määräykset ja ohjeet 2/2023"), long)
        self.assertEqual(shown_short_name(long, ""), long)

    @override_settings(INSTRUMENT_SHORT_NAME_MAX_WORDS=5)
    def test_the_word_limit_is_a_setting(self) -> None:
        self.assertEqual(shown_short_name("Lag om frysning av tillgångar", "SFS 2023:677"), "Lag om frysning av tillgångar")
