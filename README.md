# The Christmas Palace — Up To 50% OFF

Static snapshot of the public page:

https://thechristmaspalace.com/pages/up-to-50-off-sale

## Files

- `index.html` — page markup with the original copy, styling, product cards and layout.
- `source.html` — unmodified HTML downloaded from the source page.
- `assets/` — archived first-party photos, scripts and style files referenced in the HTML.
- `assets-manifest.json` — original asset URLs, local filenames, sizes, and download errors.
- `mirror.py` — repeatable one-page archival script. It does not crawl other pages.

## Preview

Serve the directory as static files, for example with `python3 -m http.server 8000`,
then open `http://localhost:8000`.

This repository is a frontend snapshot, **not** an independent Shopify store.
Product and category links lead to the original store. Live search, inventory,
cart, authentication, payment and third-party widgets continue to rely on
services provided by the original Shopify store. The page itself contains no
embedded `<video>` elements, so no video file was discovered for archiving.

No product prices, promotional text or displayed design were intentionally
changed in the snapshot.
