# Book Gutter PDF

Book Gutter PDF is a small Windows desktop utility for preparing PDFs for side binding.

It takes a normal PDF and shifts odd and even pages in opposite horizontal directions to create a mirrored binding gutter. It does not reorder pages or create booklet imposition.

## What it does

- Opens a PDF by button or drag and drop
- Shows file name, page count, page dimensions, and mixed-size status
- Lets you choose left or right binding
- Applies a mirrored horizontal shift
- Keeps scale between 80% and 100%
- Preserves page order
- Preserves vector content and selectable text in export
- Adds a blank final page for odd page counts when enabled
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

## Run

```powershell
python app.py
```

## Mirrored shifting

- Left binding: odd pages shift right, even pages shift left
- Right binding: odd pages shift left, even pages shift right

The page order stays exactly the same. This is not booklet printing.

## Shift-only mode

Use scale at 100% when you want the original size preserved. This keeps text and graphics at the original size while applying only the mirrored shift.

## Using scale

If the estimated outer margin is too small, reduce scale below 100% before exporting. Scaling happens before the mirrored shift so the content stays centered while shrinking.

## Export workflow

1. Open a PDF.
2. Choose binding side, shift, scale, and whether to add a blank final page.
3. Review the preview and clipping warnings.
4. Click **Create Print-Ready PDF**.
5. Pick a new output filename.

Suggested output names look like:

```text
OriginalName_GUTTER_5mm_100pct.pdf
```

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
