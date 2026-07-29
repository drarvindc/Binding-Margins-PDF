# Contributing to Binding Margins PDF

Thanks for helping improve Binding Margins PDF.

## Before you open a change

- Keep changes focused when practical
- Use the project-local `.venv` for development and tests
- Run `setup_book_gutter.bat` before running the test suite
- Run the test suite before opening a pull request
- Do not modify source PDFs in place
- Do not make unsupported feature claims
- Update the README for any user-visible change
- Do not rely on machine-specific or cached Python runtimes

## Code and documentation checklist

- [ ] Tests added or updated for behavior changes
- [ ] Full test suite passes
- [ ] README reviewed and updated where needed
- [ ] Source PDFs are not modified
- [ ] User-visible behavior manually verified
- [ ] Screenshots updated if the UI changed
- [ ] Known limitations remain accurate

## Documentation policy

Every user-visible feature change must include a README review.

If a change affects controls, preview behavior, page-side logic, blank-page behavior, export behavior, installation, launch process, limitations, or supported platforms, update the relevant README section in the same change.

## Reporting issues

If you open an issue, please include:

- A short description of the problem
- The source PDF characteristics that matter
- Steps to reproduce
- Your platform and Python version
- Any relevant screenshots or error messages

## Pull requests

- Explain what changed and why
- Mention any user-visible behavior changes
- Call out README updates explicitly
- Link related issues when available
