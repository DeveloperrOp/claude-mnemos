# Onboarding Polish — Manual E2E Checklist

These checks run by hand on Yarik's Win11 after merge.

## Prerequisites
- [ ] daemon restarted with new code (`mnemos daemon stop && mnemos daemon start`)
- [ ] dashboard reloaded (Ctrl+F5 to clear bundle cache)

## Display name + slug
- [ ] Open `/onboarding`
- [ ] Type "Конструктор сайтов" in Display name → slug field auto-fills with transliteration (likely `konstruktor-sajtov` or similar)
- [ ] Click «Edit slug» → slug input becomes editable; clear and type "custom-x" → display name typing no longer changes slug
- [ ] Click «Авто» → slug re-derives from current display name

## File picker
- [ ] Click «Browse» / «Обзор» next to vault path → modal opens at home dir
- [ ] Listing shows subfolders only (no files)
- [ ] Click folder row → navigate inside; breadcrumbs update
- [ ] Click breadcrumb segment → navigate to ancestor
- [ ] Click root breadcrumb (e.g. "C:") → navigates to "C:\" (drive root, NOT broken "C:")
- [ ] Type path in PathInput → Enter → navigate to that path
- [ ] Type partial name in Filter → list narrows (case-insensitive substring)
- [ ] Recent shows nothing on first use
- [ ] Click «+ Новая папка» → input dialog → type "test_pick" → Создать → folder created and navigated into
- [ ] Click «Выбрать эту папку» → modal closes; vault input shows selected path
- [ ] Reopen picker → Recent shows previously selected path
- [ ] Click recent path → navigate there
- [ ] Click «Отмена» → modal closes; vault input unchanged

## Race condition stress (DirectoryPicker fix)
- [ ] Open picker → quickly click 5 different folders one after another → final selected folder must be the LAST clicked one (no flickering / stale data from earlier clicks)
- [ ] Open picker → close (Cancel) before initial fetch completes → reopen → no errors in console

## CWD mini-builder
- [ ] Open «Расширенные» (advanced) section
- [ ] Click «Добавить папку» → DirectoryPicker opens
- [ ] Select a folder → pattern added with «Включая подпапки» checkbox checked (recursive)
- [ ] Toggle checkbox off → pattern updates (no \\* suffix)
- [ ] Toggle back on → \\* suffix returns
- [ ] Click × → pattern removed

## Display_name fallback
- [ ] Sidebar shows display name for new project, falls back to slug for old projects
- [ ] Project switcher dropdown — same
- [ ] Page headers — same
- [ ] URLs still use slug (e.g. `/project/test-cli` not `/project/Test%20Project`)

## Submit flow
- [ ] Create project «My Test Project» with vault `D:\Obsidian\mtp` (selected via Browse) and 1 cwd pattern
- [ ] Sidebar shows «My Test Project» (display_name)
- [ ] Backend `mnemos project show my-test-project` (auto-derived slug) shows display_name
- [ ] `~/.claude-mnemos/project-map.json` has display_name field set to "My Test Project"

## Clear display_name (Plan A pre-merge fix)
- [ ] `mnemos project update my-test-project --display-name ""` → mnemos project show shows display_name: -
- [ ] Sidebar reverts to showing slug

## Existing projects (no migration)
- [ ] Sidebar still shows existing 4 projects (test-cli, p, claude-mnemos, x) by slug — display_name=null fallback
- [ ] No errors loading project-map.json
