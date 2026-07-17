# Book Gutter PDF

Prepare ordinary PDFs for duplex printing and side binding without shrinking the text unnecessarily.

Book Gutter PDF is a Windows desktop utility for preparing books, manuals, zines, and similar side-bound documents. It creates mirrored binding margins, shifts odd and even pages independently, supports facing-pages preview, lets you insert intentional blank pages, and produces both print-ready and test PDFs. It is intended for home printing, stapling, tape binding, and related workflows where a book is bound on one side.

This is not booklet imposition software. It does not rearrange pages into folded signatures or place multiple pages on one sheet.

## Preview

<!-- Add application screenshot at docs/images/book-gutter-preview.png -->

The future preview image should show Single Page preview, Facing Pages preview, independent odd/even binding shifts, and the binding-space visualization.

## Why this project exists

Normal PDFs usually assume equal left and right margins. Side binding changes that assumption because the inner margin needs room for the binding edge.

Shifting every page the same way is not correct for duplex printing. Odd/right pages and even/left pages need mirrored movement, and some documents need different odd-page and even-page shift values.

Front matter and inserted blank pages can also change which side the next page occupies. That means page-side alignment has to follow the composed document sequence, not just the original page number.

Booklet tools solve a different problem. They reorder pages into signatures for folding. Book Gutter PDF keeps the original page order and applies mirrored gutter shifting instead.

## Features

### Mirrored gutter shifting

- Independent odd-page and even-page shift values
- Linked equal-shift mode for simple symmetric binding
- Left or right binding
- Millimetre-based shift controls
- 100% scale available to preserve text size

### Optional scaling

- Scaling is not required by default
- Use it only when the outer margin is too small
- The preview helps assess clipping risk before export

### Page-side alignment

- Source PDF page 1 can start on the right / odd side or the left / even side
- Side calculation follows the composed output sequence
- Inserted blanks change the side of all following pages

### Intentional blank pages

- Insert a blank before or after a selected source page
- Useful for chapter separation and controlled parity changes
- Blanks do not modify the source PDF
- Inserted blanks can be removed later

### Single-page preview

- Detailed page inspection
- Current side and shift shown in the preview details
- Estimated clipping warning
- Original-position overlay
- Binding-space display

### Facing-pages preview

- Simulates an open bound book
- Left/even page shown on the left
- Right/odd page shown on the right
- Central binding area visible
- Independent odd/even shifts visible together

### Test PDF export

- Default test export creates four pages
- Represents two duplex sheets
- Middle two pages form the facing spread being checked
- Useful before printing an entire book
- Test-padding blanks are added when needed

### Full print-ready export

- Preserves page order
- Preserves selectable/searchable text in normal cases
- Preserves vector PDF content where supported
- Does not intentionally rasterize the exported PDF
- Supports mixed page sizes
- Optionally appends a final duplex blank page
- Writes through a temporary file for safer output

### Safety and usability

- Source PDF remains untouched
- Progress and cancellation support
- Clipping warnings are advisory
- Duplicate simultaneous exports are blocked in the UI
- Windows launcher files resolve the project directory correctly

## How it works

1. The user chooses whether source PDF page 1 starts on the right / odd side or the left / even side.
2. The application builds a composed output sequence.
3. Intentional blank pages are inserted into that sequence.
4. Each output position is assigned a physical book side.
5. Right / odd and left / even pages receive their configured mirrored shifts.
6. Preview shows the expected result.
7. Test PDF export allows a small physical print check.
8. Full export produces the final print-ready PDF.

Example when source PDF page 1 starts Right / Odd:

- output 1: source page 1 - Right / Odd
- output 2: source page 2 - Left / Even
- inserted blank before source page 3
- output 3: intentional blank - Right / Odd
- output 4: source page 3 - Left / Even

The inserted blank changes the side of all following pages.

## Facing spreads versus duplex sheets

This distinction matters.

Facing-page preview examples:

- 2-3
- 4-5
- 6-7

Physical duplex sheet pairs:

- 1-2
- 3-4
- 5-6

For target facing spread 8-9, the four-page Test PDF exports:

- 7
- 8
- 9
- 10

Physical sheets:

- sheet 1: 7 front / 8 back
- sheet 2: 9 front / 10 back

When opened, pages 8 and 9 form the inspected facing spread.

Facing Pages preview does not reorder full PDF export.

## Screenshots

### Main window

<!-- Add main window screenshot at docs/images/book-gutter-main-window.png -->

### Single-page preview

<!-- Add single-page preview screenshot at docs/images/book-gutter-single-page-preview.png -->

### Facing-pages preview

<!-- Add facing-pages preview screenshot at docs/images/book-gutter-facing-pages-preview.png -->

### Intentional blank-page controls

<!-- Add intentional blank-page controls screenshot at docs/images/book-gutter-blank-controls.png -->

### Test PDF export dialog

<!-- Add test PDF export dialog screenshot at docs/images/book-gutter-test-export-dialog.png -->

## Project status

- Working desktop application
- Tested locally on Windows
- Source-based launch is currently available
- Packaging and a user-friendly installer are not yet published
- The project is under active development
- The repository includes an automated pytest suite covering layout, parity, preview, export, and threading behaviour

## Installation and launch

Book Gutter PDF is meant to run from a project-local `.venv` on Windows.

### First-time setup

Run:

```powershell
setup_book_gutter.bat
```

PowerShell alternative:

```powershell
.\setup_book_gutter.ps1
```

The setup scripts create `.venv`, install the dependencies from `requirements.txt`, and verify that `fitz`, `PySide6`, and `numpy` import correctly.

Do not rely on Codex's cached Python runtime. The project should use the local `.venv`.

### Normal launch

Run:

```powershell
Book Gutter PDF.bat
```

PowerShell alternative:

```powershell
.\launch_book_gutter.ps1
```

You can also use `launch_book_gutter.bat`.

The launchers prefer `.venv\Scripts\python.exe` and will tell you to run the setup script if the environment is missing or incomplete.

If you see:

```text
ModuleNotFoundError: No module named 'fitz'
```

that means PyMuPDF is not installed in the Python environment being used. The fix is to run `setup_book_gutter.bat`.

## Quick start

1. Open a PDF.
2. Choose left or right binding.
3. Set whether source PDF page 1 is right / odd or left / even.
4. Choose odd and even shifts.
5. Keep scale at 100% initially.
6. Inspect Single Page and Facing Pages previews.
7. Insert intentional blanks where chapters need separation.
8. Create a four-page Test PDF.
9. Print it duplex and check the physical binding.
10. Adjust shifts or scaling if needed.
11. Create the full print-ready PDF.
12. Print normally at actual size or 100%.

Printer reload orientation can vary, so test your printer's duplex behavior separately before relying on a large run.

## Blank page types

### Intentional blank

- User-created
- Part of the full document layout
- Changes the parity of following pages

### Automatic final blank

- Optional
- Added only to complete an odd-page full export
- Not stored as an intentional blank

### Test-padding blank

- Exists only in Test PDF export
- Ensures four test output pages
- Does not alter the full document layout

## Clipping and scaling

- Shifting at 100% preserves text size
- The outer margin becomes smaller when content shifts outward
- The preview estimates visible content bounds
- Warnings are advisory, not guaranteed
- Faint content may not always be detected
- Scaling is available when the source has insufficient outer margin
- Physical test printing remains the final check

## PDF quality

Export uses PDF page placement rather than screenshot conversion. That means it aims to retain selectable text, vector shapes, and images in normal cases.

Like many PDF tools, there can be limitations around some annotations, internal links, form fields, or unusual PDF structures.

## Requirements

- Windows is the currently tested platform
- Python 3
- PySide6
- PyMuPDF
- NumPy
- pytest for development and testing

The code may work on other desktop platforms, but they are not currently documented or tested.

## Development

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```

The codebase keeps GUI, layout, transformation, preview, and export logic separated into smaller modules. The automated tests generate temporary PDFs and verify layout, parity, preview pairing, export behavior, and threading behavior. Source PDFs must never be modified in place.

Repository structure at a glance:

```text
app.py
src/book_gutter/
tests/
docs/
```

## Roadmap

- [ ] Packaged Windows EXE
- [ ] Installer
- [ ] Release downloads
- [ ] Application icon and branding
- [ ] Saved project and layout settings
- [ ] Batch processing
- [ ] More detailed all-page margin scanning
- [ ] Improved annotation and internal-link preservation
- [ ] Additional platform testing
- [ ] Automated GitHub Actions test workflow
- [ ] Screenshot and demo GIF documentation

## Known limitations

- Clipping detection is estimated
- The user must determine the correct physical printer reloading direction
- This is not booklet or signature imposition
- There is no direct printer integration
- There is no OCR of printed page numbers
- Page-side alignment is user-defined
- Unusual annotations, forms, or internal links may not be fully preserved
- There is no packaged public installer yet
- The project is currently tested primarily on Windows

## Contributing

Issues and pull requests are welcome.

- Open an issue for bugs or feature requests
- Include source PDF characteristics without uploading copyrighted material unnecessarily
- Include steps to reproduce
- Include the platform and Python version you used
- Run the tests before opening a pull request
- Update tests for behavioral changes
- Update the README for user-visible changes

## Documentation policy

Every user-visible feature change must include a README review.

Any change that affects controls, preview behavior, page-side logic, blank-page behavior, export behavior, installation, launch process, limitations, or supported platforms must update the relevant README section in the same change.

## License

A project license has not yet been selected. Until a license is added, normal copyright restrictions apply.

## Built with

- Python
- PySide6
- PyMuPDF
- pytest
