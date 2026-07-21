"""Public-domain liturgical texts for the Daily Office rites (LWS occasion services).

DELIBERATELY SEPARATE from ``static_text.py``.  ``static_text.py`` bundles
ELW-2006 / ELLC / Setting Two wording, which is copyrighted and only lawfully
distributed to a *licensed* deployment.  Everything in this module is genuinely
public domain (1662/1928 Book of Common Prayer, the King James Version, or a
pre-1929 hymn translation) and may be bundled and distributed unconditionally.
Keeping the two families in separate modules is what lets a future entitlement
layer gate the ELW wording while always shipping the PD fallback.

Each constant carries a comment naming its PD source.  These are the
bundled *defaults*; a church entitled to ELW resolves ELW's contemporary
wording (the ELLC canticles, ELW's Service of Light dialogue, ELW's
responsories/collects) as a licensed overlay that is NOT authored here.

DRAFT for owner verification.  The three gospel canticles were transcribed
verbatim from a fetched KJV source (bible-api.com) and cross-checked against
the World English Bible (ebible.org); the 1662 BCP and Bridges texts are the
standard fixed PD forms and should be spot-checked against a 1662 BCP / hymnal.

See ``docs/research/2026-07-liturgy-strategy/10-pd-text-sourcing.md`` for the
[PD-BUNDLE] manifest and the copyright corrections that govern this file.
"""

from __future__ import annotations

from bulletin_maker.core.text_utils import DialogRole

# ── Gospel canticles (King James Version, 1611 — public domain) ────────
# The KJV is public domain in the United States.  Transcribed verbatim from
# a fetched KJV source and cross-checked against the World English Bible.

# Benedictus — Song of Zechariah, Luke 1:68-79 (KJV).
PD_BENEDICTUS_KJV = (
    "Blessed be the Lord God of Israel; "
    "for he hath visited and redeemed his people,\n"
    "and hath raised up an horn of salvation for us "
    "in the house of his servant David;\n"
    "as he spake by the mouth of his holy prophets, "
    "which have been since the world began:\n"
    "that we should be saved from our enemies, "
    "and from the hand of all that hate us;\n"
    "to perform the mercy promised to our fathers, "
    "and to remember his holy covenant;\n"
    "the oath which he sware to our father Abraham,\n"
    "that he would grant unto us, that we being delivered "
    "out of the hand of our enemies "
    "might serve him without fear,\n"
    "in holiness and righteousness before him, "
    "all the days of our life.\n"
    "And thou, child, shalt be called the prophet of the Highest: "
    "for thou shalt go before the face of the Lord to prepare his ways;\n"
    "to give knowledge of salvation unto his people "
    "by the remission of their sins,\n"
    "through the tender mercy of our God; "
    "whereby the dayspring from on high hath visited us,\n"
    "to give light to them that sit in darkness "
    "and in the shadow of death, "
    "to guide our feet into the way of peace."
)

# Magnificat — Song of Mary, Luke 1:46-55 (KJV).
PD_MAGNIFICAT_KJV = (
    "And Mary said, My soul doth magnify the Lord,\n"
    "and my spirit hath rejoiced in God my Saviour.\n"
    "For he hath regarded the low estate of his handmaiden: "
    "for, behold, from henceforth all generations shall call me blessed.\n"
    "For he that is mighty hath done to me great things; "
    "and holy is his name.\n"
    "And his mercy is on them that fear him "
    "from generation to generation.\n"
    "He hath shewed strength with his arm; "
    "he hath scattered the proud in the imagination of their hearts.\n"
    "He hath put down the mighty from their seats, "
    "and exalted them of low degree.\n"
    "He hath filled the hungry with good things; "
    "and the rich he hath sent empty away.\n"
    "He hath holpen his servant Israel, "
    "in remembrance of his mercy;\n"
    "as he spake to our fathers, "
    "to Abraham, and to his seed for ever."
)

# Nunc Dimittis — Song of Simeon, Luke 2:29-32 (KJV).
PD_NUNC_DIMITTIS_KJV = (
    "Lord, now lettest thou thy servant depart in peace, "
    "according to thy word:\n"
    "for mine eyes have seen thy salvation,\n"
    "which thou hast prepared before the face of all people;\n"
    "a light to lighten the Gentiles, "
    "and the glory of thy people Israel."
)

# ── Te Deum Laudamus (1662 Book of Common Prayer — public domain) ──────
# The standard fixed 1662 BCP English text (Morning Prayer canticle).
PD_TE_DEUM_BCP1662 = (
    "We praise thee, O God: we acknowledge thee to be the Lord.\n"
    "All the earth doth worship thee: the Father everlasting.\n"
    "To thee all Angels cry aloud: "
    "the Heavens, and all the Powers therein.\n"
    "To thee Cherubin and Seraphin: continually do cry,\n"
    "Holy, Holy, Holy: Lord God of Sabaoth;\n"
    "Heaven and earth are full of the Majesty: of thy glory.\n"
    "The glorious company of the Apostles: praise thee.\n"
    "The goodly fellowship of the Prophets: praise thee.\n"
    "The noble army of Martyrs: praise thee.\n"
    "The holy Church throughout all the world: doth acknowledge thee;\n"
    "the Father: of an infinite Majesty;\n"
    "thine honourable, true: and only Son;\n"
    "also the Holy Ghost: the Comforter.\n"
    "Thou art the King of Glory: O Christ.\n"
    "Thou art the everlasting Son: of the Father.\n"
    "When thou tookest upon thee to deliver man: "
    "thou didst not abhor the Virgin's womb.\n"
    "When thou hadst overcome the sharpness of death: "
    "thou didst open the Kingdom of Heaven to all believers.\n"
    "Thou sittest at the right hand of God: in the glory of the Father.\n"
    "We believe that thou shalt come: to be our Judge.\n"
    "We therefore pray thee, help thy servants: "
    "whom thou hast redeemed with thy precious blood.\n"
    "Make them to be numbered with thy Saints: in glory everlasting.\n"
    "O Lord, save thy people: and bless thine heritage.\n"
    "Govern them: and lift them up for ever.\n"
    "Day by day: we magnify thee;\n"
    "and we worship thy Name: ever world without end.\n"
    "Vouchsafe, O Lord: to keep us this day without sin.\n"
    "O Lord, have mercy upon us: have mercy upon us.\n"
    "O Lord, let thy mercy lighten upon us: as our trust is in thee.\n"
    "O Lord, in thee have I trusted: let me never be confounded."
)

# ── Phos Hilaron (Robert Bridges, 1899 — public domain) ────────────────
# "O gladsome light" — Bridges' pre-1929 English translation of the ancient
# Greek Phos Hilaron.  Public domain in the United States.
PD_PHOS_HILARON_BRIDGES = (
    "O gladsome light, O grace\n"
    "of God the Father's face,\n"
    "the eternal splendour wearing;\n"
    "celestial, holy, blest,\n"
    "our Saviour Jesus Christ,\n"
    "joyful in thine appearing.\n"
    "\n"
    "Now, ere day fadeth quite,\n"
    "we see the evening light,\n"
    "our wonted hymn outpouring;\n"
    "Father of might unknown,\n"
    "thee, his incarnate Son,\n"
    "and Holy Spirit adoring.\n"
    "\n"
    "To thee of right belongs\n"
    "all praise of holy songs,\n"
    "O Son of God, Life-giver;\n"
    "thee, therefore, O Most High,\n"
    "the world doth glorify,\n"
    "and shall exalt for ever."
)

# ── Opening versicles (1662/1928 BCP — public domain) ──────────────────
# Morning Prayer opening versicles (Ps 51:15 / Ps 70:1).
PD_VERSICLE_OPEN_LIPS = [
    (DialogRole.PASTOR, "O Lord, open thou our lips."),
    (DialogRole.CONGREGATION, "And our mouth shall shew forth thy praise."),
]

PD_VERSICLE_MAKE_SPEED = [
    (DialogRole.PASTOR, "O God, make speed to save us."),
    (DialogRole.CONGREGATION, "O Lord, make haste to help us."),
]

# ── Gloria Patri (traditional doxology, 1662 BCP form — public domain) ─
PD_GLORIA_PATRI = (
    "Glory be to the Father, and to the Son, "
    "and to the Holy Ghost;\n"
    "as it was in the beginning, is now, and ever shall be, "
    "world without end. Amen."
)

# ── General Confession (1662 BCP Morning/Evening Prayer — public domain)
# Used in the Night Prayer rite as the PD substitute for ELW's Compline
# confession (a working substitute, NOT verbatim ELW — see doc 10 §Flagged).
PD_GENERAL_CONFESSION_BCP = (
    "Almighty and most merciful Father;\n"
    "we have erred, and strayed from thy ways like lost sheep.\n"
    "We have followed too much the devices and desires of our own hearts.\n"
    "We have offended against thy holy laws.\n"
    "We have left undone those things which we ought to have done;\n"
    "and we have done those things which we ought not to have done;\n"
    "and there is no health in us.\n"
    "But thou, O Lord, have mercy upon us, miserable offenders.\n"
    "Spare thou them, O God, which confess their faults.\n"
    "Restore thou them that are penitent;\n"
    "according to thy promises declared unto mankind "
    "in Christ Jesu our Lord.\n"
    "And grant, O most merciful Father, for his sake;\n"
    "that we may hereafter live a godly, righteous, and sober life,\n"
    "to the glory of thy holy Name. Amen."
)

# ── Compline / Night Prayer (traditional PD forms) ─────────────────────
# Opening (and closing benediction) versicle of the traditional Compline
# office; medieval origin, PD in English use.  ELW's contemporary "quiet
# night and peace at the last" wording is [LIC] and not bundled here.
PD_COMPLINE_OPEN = (
    "The Lord Almighty grant us a quiet night and a perfect end.\n"
    "Amen."
)

# Compline responsory (Ps 31:5 / Luke 23:46) — traditional PD form.
PD_INTO_THY_HANDS = [
    (DialogRole.PASTOR, "Into thy hands, O Lord, I commend my spirit;"),
    (
        DialogRole.CONGREGATION,
        "for thou hast redeemed me, O Lord, thou God of truth.",
    ),
]
