# Kimi review: staged release version guard

Date: 2026-07-15.

## Scope

Independent review of the local guard that requires a higher HausmanHub version when
a prepared change touches the integration package or `hacs.json`.

## Review and correction

The first independent review found that a change of file type was not included
in the list of checked Git changes. The guard was corrected to include it, and
a focused test now covers both removal and file-type change.

## Final result

Kimi session `ses_09bc8d608ffetMIxy8tm7fdq4d` reviewed the corrected staged
changes and reported: `Находок нет.`

The check reads only local Git data. No Home Assistant, home data, device, or
network access was used.
