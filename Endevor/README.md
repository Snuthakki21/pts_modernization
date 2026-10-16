# Endevor source views

Put approved, sanitized mainframe export files in this folder, retaining their
library/type organization. Keep protected originals in the existing source store.
Do not copy a denied source here to bypass access controls. The folder name alone
does not establish approval or prove that an export came from Endevor SCM.

The lead records explicit files, qualified identities, encodings and the existing
approval reference in local `Endevor/navigation.json`. Start from
[the empty manifest](../templates/endevor/navigation.json) and follow
[Endevor navigation](../docs/ENDEVOR_NAVIGATION.md).

Source files, the populated manifest and generated navigation stay out of Git.
Only this guide is tracked. No mainframe artifacts are supplied with the kit.
