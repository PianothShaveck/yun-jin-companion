#!/usr/bin/env python3
"""Inventory translation surfaces; this is NOT a completeness certification.

Records literal/f-string arguments at known UI, validation and guide call sites.
Indirect strings (tables, labels passed through variables, native controls,
scripts, generated text) require manual review and are listed as separate work.
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path

CALLS = set('''QLabel QPushButton QCheckBox QRadioButton QGroupBox QAction
plain_label button icon_button setText setWindowTitle setToolTip setStatusTip
setPlaceholderText setAccessibleName setAccessibleDescription setSuffix setPrefix
addItem addItems addAction addTab addRow setHeaderLabels setTabText
critical warning information question getOpenFileName getSaveFileName
getExistingDirectory ValueError RuntimeError p h table call'''.split())


def audit(root):
    records, totals = [], Counter()
    paths = sorted((root/'app').glob('*.py')) + sorted((root/'installer').glob('*.py'))
    paths += [root/'docs/build_guide.py']
    for path in paths:
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
            if name not in CALLS:
                continue
            for arg in node.args:
                # Keep the whole f-string rather than pretending its fragments are messages.
                if isinstance(arg, ast.JoinedStr):
                    value = ast.get_source_segment(source, arg)
                    dynamic = True
                elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    value, dynamic = arg.value, False
                else:
                    continue
                if not value.strip():
                    continue
                rel = path.relative_to(root).as_posix()
                totals[rel] += 1
                records.append(dict(file=rel, line=arg.lineno, call=name,
                                    dynamic=dynamic, text=value))
    return dict(kind='candidate call-site inventory, not a translation catalog',
                count=len(records), unique_candidates=len({r['text'] for r in records}),
                by_file=dict(sorted(totals.items())), records=records,
                manual_review=['arguments through variables and data tables',
                               'month/day names, plurals, units, date/time formatting',
                               'native Qt dialogs and accessibility labels',
                               'installer shell/PowerShell/launchers and startup failures',
                               'guide tables, HTML fragments, screenshots and CJK fonts',
                               'README, release notes, GitHub description',
                               'voice selection separate from interface language',
                               'existing translated greeting/weather pools',
                               'AI prompts, error propagation and text coming from services'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','manual_review')}, indent=2))


if __name__ == '__main__':
    main()
