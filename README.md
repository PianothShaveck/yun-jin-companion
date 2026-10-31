# Yun Jin Companion

A desktop companion with notes, reminders, a calendar, alarms, flashcards, weather, a metronome and a stopwatch.

English is the default. Choose **English**, **Italiano** or **简体中文** on first launch. The interface and guide are available in all three languages. Voice language is independent.

## Install

Download the application ZIP from [Releases](https://github.com/PianothShaveck/yun-jin-companion/releases/latest) and extract it completely.

- **Windows 10/11, 64-bit:** open `Windows.cmd`.
- **macOS 13 or later:** open `Mac.command`.
- **Linux:** install a supported Python and `python3-venv`, then run `sh Linux.sh`.

The installer prepares a separate Python environment and creates an application shortcut. Internet is required for installation. To update an existing installation, close Yun Jin and run the new installer; personal data is retained.

## Use

Double-click Yun Jin to open the panel; right-click for the menu. Hiding the character keeps tools, alarms and reminders available. Customize shortcuts in Settings.

The calendar supports recurring events, daily illustrations and optional two-way Google Calendar sync. Choose which calendars to sync, or keep events only on the current device. Offline edits are retained; conflicting edits can be kept as separate copies.

Study includes FSRS flashcards and optional read-only practice from Anki. Notes, alarms, study and music tools work offline. Voice, weather, updates, Google sync and uncached calendar originals require Internet.

[English guide](Guide.pdf) · [Guida italiana](Guida.pdf) · [简体中文指南](Guide.zh-CN.pdf)

## Data and privacy

Settings provides **Backup** and **Data folder**. Linked files remain at their original paths. Google credentials use the system keychain; backups restore as local data without reconnecting accounts. Voice text goes to the selected speech service; weather uses the chosen city's coordinates.

## License

Code: [GPL-3.0-or-later](app/licenses/GPL-3.0.txt). Dependency licenses are retained by their packages. Weather: [Open-Meteo](https://open-meteo.com/), CC BY 4.0; city search: GeoNames.

Unofficial fan project. Yun Jin and Genshin Impact belong to their respective rights holders. No affiliation with HoYoverse, Microsoft, Google or OpenAI.
