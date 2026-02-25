"""
Generate test documents for Feb 22, 2026 (Lent 1A).

Usage:
    source venv/bin/activate
    python scripts/generate_test.py

Produces PDF files (via HTML/CSS + Playwright) in output/ directory.
Compare against examples/-02-2026 February/ASCENSION -- 2026.02.22 LENT 1A/
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bulletin_maker.sns import SundaysClient, HymnLyrics, ServiceConfig
from bulletin_maker.renderer import (
    generate_pulpit_scripture,
    generate_pulpit_prayers,
    generate_large_print,
)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"
DATE = "2026-2-22"
DATE_DISPLAY = "February 22, 2026"


# ── Sample hymn lyrics for Lent 1A (from LP reference) ──────────────

GATHERING_HYMN = HymnLyrics(
    number="ELW 335",
    title="Jesus, Keep Me Near the Cross",
    verses=[
        "1\tJesus, keep me near the cross,\n"
        "there's a precious fountain;\n"
        "free to all, a healing stream\n"
        "flows from Calv'ry's mountain.",
        "2\tNear the cross, a trembling soul,\n"
        "love and mercy found me;\n"
        "there the bright and morning star\n"
        "sheds its beams around me.  Refrain",
        "3\tNear the cross! O Lamb of God,\n"
        "bring its scenes before me;\n"
        "help me walk from day to day\n"
        "with its shadow o'er me.  Refrain",
        "4\tNear the cross I'll watch and wait, hoping, trusting ever,\n"
        "till I reach the golden strand\n"
        "just beyond the river.  Refrain",
    ],
    refrain=(
        "In the cross, in the cross\n"
        "be my glory ever;\n"
        "till my ransomed soul shall find\n"
        "rest beyond the river."
    ),
    copyright="Text: Fanny J. Crosby, 1820-1915",
)

SERMON_HYMN = HymnLyrics(
    number="ELW 319",
    title="O Lord, Throughout These Forty Days",
    verses=[
        "1\tO Lord, throughout these forty days you prayed and kept the fast;\n"
        "inspire repentance for our sin, and free us from our past.",
        "2\tYou strove with Satan, and you won; your faithfulness endured;\n"
        "lend us your nerve, your skill, and trust in God's eternal word.",
        "3\tThough parched and hungry, yet you prayed and fixed your mind above;\n"
        "so teach us to deny ourselves, since we have known God's love.",
        "4\tBe with us through this season, Lord, and all our earthly days,\n"
        "that when the final Easter dawns, we join in heaven's praise.",
    ],
    copyright=(
        "Text: based on Claudia F. Hernaman, 1838-1898; para. Gilbert E. Doan Jr., b. 1930\n"
        "Text \u00a9 1978 Lutheran Book of Worship, admin. Augsburg Fortress."
    ),
)

COMMUNION_HYMN = HymnLyrics(
    number="ELW 512",
    title="Lord, Let My Heart Be Good Soil",
    verses=[
        "Lord, let my heart be good soil,\n"
        "open to the seed of your word.\n"
        "Lord, let my heart be good soil,\n"
        "where love can grow and peace is understood.",
        "When my heart is hard,\nbreak the stone away.\n"
        "When my heart is cold,\nwarm it with the day.\n"
        "When my heart is lost,\nlead me on your way.\n"
        "Lord, let my heart,\nLord, let my heart,\n"
        "Lord, let my heart be good soil.",
    ],
    copyright=(
        "Text: Handt Hanson, b. 1950\n"
        "Text \u00a9 1985 Prince of Peace Publishing, Changing Church, Inc., "
        "admin. Augsburg Fortress."
    ),
)

SENDING_HYMN = HymnLyrics(
    number="ELW 333",
    title="Jesus Is a Rock in a Weary Land",
    verses=[
        "Jesus is a rock in a weary land, a weary land, a weary land;\n"
        "my Jesus is a rock in a weary land, a shelter in the time of storm.",
        "1\tNo one can do like Jesus,\n"
        "not a mumbling word he said;\n"
        "he went walking down to Lazarus' grave,\n"
        "and he raised him from the dead.  Refrain",
        "2\tWhen Jesus was on earth,\n"
        "the flesh was very weak;\n"
        "he took a towel and girded himself\n"
        "and he washed his disciples' feet.  Refrain",
        "3\tYonder comes my Savior,\n"
        "him whom I love so well;\n"
        "he has the palm of victory\n"
        "and the keys of death and hell.  Refrain",
    ],
    copyright="Text: African American spiritual",
)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("Generating Documents for Lent 1A (Feb 22, 2026)")
    print("=" * 60)

    print("\n1. Fetching content from Sundays & Seasons...")
    with SundaysClient() as client:
        day = client.get_day_texts(DATE)

    print(f"   Title: {day.title}")
    print(f"   Readings: {len(day.readings)}")
    for r in day.readings:
        print(f"     {r.label}: {r.citation}")
    print(f"   Prayers HTML length: {len(day.prayers_html)} chars")
    print(f"   Offering Prayer: {len(day.offering_prayer_html)} chars")
    print(f"   Blessing: {len(day.blessing_html)} chars")
    print(f"   Dismissal: {len(day.dismissal_html)} chars")

    print("\n2. Generating Pulpit Scripture PDF...")
    scripture_path = generate_pulpit_scripture(
        day, DATE_DISPLAY, OUTPUT_DIR / "Pulpit SCRIPTURE 8.5 x 11.pdf"
    )
    print(f"   Saved: {scripture_path}")

    print("\n3. Generating Pulpit Prayers PDF...")
    prayers_path = generate_pulpit_prayers(
        day, DATE_DISPLAY,
        creed_type="nicene",
        creed_page_num=None,
        output_path=OUTPUT_DIR / "Pulpit PRAYERS + NICENE 8.5 x 11.pdf",
    )
    print(f"   Saved: {prayers_path}")

    print("\n4. Generating Large Print PDF...")
    config = ServiceConfig(
        date=DATE,
        date_display=DATE_DISPLAY,
        creed_type="nicene",
        gathering_hymn=GATHERING_HYMN,
        sermon_hymn=SERMON_HYMN,
        communion_hymn=COMMUNION_HYMN,
        sending_hymn=SENDING_HYMN,
    )
    lp_path = generate_large_print(
        day, config,
        output_path=OUTPUT_DIR / "Full with Hymns LARGE PRINT.pdf",
    )
    print(f"   Saved: {lp_path}")

    print("\n" + "=" * 60)
    print(f"Done! Files in: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
