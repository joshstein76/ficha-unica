Fonts for the share cards (llave/cards.py)
==========================================

Bundled here (so the server never needs system fonts):

  Figtree-500.ttf   Figtree Medium    body text on the cards
  Figtree-600.ttf   Figtree SemiBold  bold text, and the headline / price fallback

Figtree: Copyright 2022 The Figtree Project Authors.
Licence: SIL Open Font License, Version 1.1 (https://openfontlicense.org).
The licence permits bundling and use in software. The full licence text file (OFL.txt)
was not available offline when these files were added: put the upstream OFL.txt next to
the fonts before the repository is made public or the fonts are redistributed.

Brand display fonts (optional, NOT bundled yet)
-----------------------------------------------
The brand headline fonts are Shrikhand (card titles) and Bricolage Grotesque ExtraBold
(prices). If these files exist the cards use them, otherwise the cards use bold Figtree
(SemiBold with a thicker outline), which looks right on its own. Drop the files in this
folder, or in the folder named by LLAVE_CARD_FONTS_DIR:

  Shrikhand-Regular.ttf
  BricolageGrotesque-ExtraBold.ttf
      (or the variable file BricolageGrotesque[opsz,wdth,wght].ttf, or
       BricolageGrotesque-Variable.ttf, or BricolageGrotesque-Bold.ttf)

Both are SIL Open Font License fonts from Google Fonts. Put each licence file next to its font.

LLAVE_CARD_FONT=/path/to/font.ttf still works: it forces that one font for every card text.
