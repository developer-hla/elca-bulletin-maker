"""
Test the S&S client — verifies login, day texts, and music search.
Run: python -m pytest tests/test_sns_client.py -s
"""

from bulletin_maker.sns import SundaysClient


def main():
    with SundaysClient() as client:
        # --- Test 1: Login ---
        print("=" * 60)
        print("TEST 1: Login")
        print("=" * 60)
        client.login()
        print()

        # --- Test 2: Fetch DayTexts ---
        print("=" * 60)
        print("TEST 2: Fetch DayTexts for 2026-2-22")
        print("=" * 60)
        day = client.get_day_texts("2026-2-22")
        print(f"  Title: {day.title}")
        print(f"  Introduction length: {len(day.introduction)}")
        print(f"  Confession HTML length: {len(day.confession_html)}")
        print(f"  Prayer of the Day HTML length: {len(day.prayer_of_the_day_html)}")
        print(f"  Gospel Acclamation length: {len(day.gospel_acclamation)}")
        print(f"  Readings found: {len(day.readings)}")
        for r in day.readings:
            print(f"    {r.label}: {r.citation} ({len(r.text_html)} chars)")
        print()

        # --- Test 3: Music Search by number ---
        print("=" * 60)
        print("TEST 3: Search for ELW hymns by number")
        print("=" * 60)
        for num in ["504", "779", "151"]:
            results = client.search_hymn(num)
            print(f"\n  ELW {num}: {len(results)} result(s)")
            for r in results:
                print(f"    atomId={r.atom_id}: {r.title}")
                print(f"      Numbers: {r.hymn_numbers}")
                print(f"      Harmony={r.harmony_atom_id} Melody={r.melody_atom_id} Words={r.words_atom_id}")
        print()

        # --- Test 4: Hymn Details ---
        results = client.search_hymn("504")
        if results:
            hymn = results[0]
            print("=" * 60)
            print(f"TEST 4: Details for '{hymn.title}' (atomId={hymn.atom_id})")
            print("=" * 60)
            detail = client.get_hymn_details(hymn.atom_id)
            print(f"  atomCode: {detail.atom_code}")
            print(f"  Harmony image: {detail.harmony_image_url}")
            print(f"  Melody image: {detail.melody_image_url}")
            print(f"  Copyright length: {len(detail.copyright_html)}")

            # --- Test 5: Download an image ---
            img_url = detail.melody_image_url or detail.harmony_image_url
            if img_url:
                print()
                print("=" * 60)
                print("TEST 5: Download notation image")
                print("=" * 60)
                img_bytes = client.download_image(img_url)
                print(f"  Downloaded {len(img_bytes)} bytes")

        print()
        print("All tests complete.")


if __name__ == "__main__":
    main()
