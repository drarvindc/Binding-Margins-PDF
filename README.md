# Book Gutter PDF

Book Gutter PDF is a small Windows desktop utility for preparing PDFs for side binding.

It takes a normal PDF and shifts odd and even pages in opposite horizontal directions to create a mirrored binding gutter. It does not reorder pages or create booklet imposition.

## Recommended launch

The easiest way to start the app is:

```text
launch_book_gutter.bat
```

You can also run:

```powershell
.\launch_book_gutter.ps1
```

The convenience shortcut target is:

```text
Book Gutter PDF.bat
```

## What it does

- Opens a PDF by button or drag and drop
- Shows file name, page count, page dimensions, and mixed-size status
- Lets you choose left or right binding
- Lets you choose whether the document starts on the right / odd side or the left / even side
- Applies a mirrored horizontal shift
- Lets you switch the preview between Single Page and Facing Pages
- Keeps scale between 80% and 100%
- Preserves page order
- Preserves vector content and selectable text in export
- Lets you insert intentional blank pages before or after any source page
- Can append an automatic final blank page for odd-length exports when enabled
- Exports a print-ready PDF to a new file

## What it does not do

- Booklet or signature imposition
- 2-up or 4-up printing
- Automatic printer control
- Direct printing
- OCR
- Page reordering
- Crop-box editing
- Automatic document-wide margin scanning

## Installation

Create a virtual environment:

```powershell
py -3.11 -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Why the launcher matters

Running this from `C:\WINDOWS\system32`:

```powershell
python app.py
```

fails because `app.py` is resolved relative to the current working directory. The launchers in this repository resolve their own folder first, change into the project directory, and then start `app.py` with the right interpreter.

## Run directly

```powershell
python app.py
```

## Mirrored shifting

- Left binding: odd pages shift right, even pages shift left
- Right binding: odd pages shift left, even pages shift right

Odd and even pages can use the same shift value, which is the default for simple symmetric binding. You can also unlink them for asymmetric binding needs, for example odd pages at 11 mm and even pages at 15 mm.

The page order stays exactly the same. This is not booklet printing.

## Shift-only mode

Use scale at 100% when you want the original size preserved. This keeps text and graphics at the original size while applying only the mirrored shift.

## Using scale

If the estimated outer margin is too small, reduce scale below 100% before exporting. Scaling happens before the mirrored shift so the content stays centered while shrinking.

## Export workflow

1. Open a PDF.
2. Choose the document first-page side, binding side, odd and even shift values, scale, preview mode, and whether to add a blank final page.
3. Review the preview and clipping warnings.
4. Click **Create Print-Ready PDF**.
5. Pick a new output filename.

Facing Pages preview shows the document as an open bound book:

- Page 1 appears alone on the right, with an inside-cover placeholder on the left
- Even pages are shown on the left and odd pages on the right
- The preview keeps the original page order and does not reorder pages for export

This preview mode is separate from test export pairing. The preview shows how the book opens visually, while test export still uses physical duplex sheet pairs for quick printer checks.

Suggested output names look like:

```text
OriginalName_GUTTER_5mm_100pct.pdf
```

## Test export

Use **Create Test PDF** when you want a small duplex check instead of a full export.

Two options are available:

- Two duplex sheets - 4 pages
- Custom page range

The default quick test exports two back-to-back sheets, which gives you four pages to inspect in one go. The middle two pages form a facing spread, so you can check odd and even page movement, front and back, and both binding margins together.

For example, if you test page 9, the app exports pages 7-10 so the middle spread is 8-9.

That pairing is for the test PDF only. The Facing Pages preview is purely visual and does not change export order or test-export sheet selection.

Custom ranges can automatically expand to complete duplex pairs. For example:

- `2-5` becomes `1-6`
- `4-4` becomes `3-4`

If a selected range ends on the final unmatched odd page, a blank partner page is appended so the duplex test still has two sides.

If you insert intentional blank pages in the document, they are preserved in both full export and test export. That means later pages can flip parity after the blank, which is useful when you need a deliberate gutter break or a cover-like opening.

The composed page-side assignment is preserved during test export. Page 10 still uses even-page movement in a normal document, but an inserted blank can shift later pages onto the opposite side.

The app does not read page numbers from artwork. It uses the document order and the configured first-page side to decide which pages are odd or even.

## Estimated clipping detection

The app includes a geometry warning and a best-effort content-edge estimate. The estimate is based on a low-resolution preview and near-white thresholding, so it can miss very light artwork or faint content.

## Duplex printing

After export, print the new PDF duplex on normal A4 paper with the binding edge you selected:

- Left binding: staple or tape on the left edge
- Right binding: staple or tape on the right edge

## Notes

- The source PDF is never modified.
- The exported PDF is written to a temporary file first and only moved into place after a successful export.
- Mixed page sizes are preserved.
- The output folder can be opened after a successful export.
