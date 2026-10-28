# Publication privacy and security review

Review date: October 28, 2026. Scope: the source snapshot selected for publication, including vendored sources, the thesis PDF and image metadata. Local archived prototypes were reviewed as well but are excluded from the final publication. This review concerns accidental disclosure in the repository; it is not a penetration test or a dependency vulnerability assessment.

## Privacy policy

The author requested that only academic attribution be retained. Author and supervisor names, institutional attribution and the public project identity remain. Personal mailboxes, machine-specific home paths, credentials, local environments and complete run recordings must not be published. Upstream copyright notices, license text and already-public maintainer contacts remain part of the vendored dependencies.

## Findings and corrections

- A personal mailbox appeared in six project metadata files: `setup.py` and `package.xml` in each of the three project ROS packages. These entries now use a GitHub `noreply` address.
- An archived prompt-testing prototype contained a machine-specific absolute path. It now resolves the behavior prompt relative to the repository.
- Ignore rules were expanded to cover additional private-key containers, SSH identities, credential JSON files, password databases and environment-file names.
- No values from the local credential-bearing environment configuration were found in the publication candidates. Checks compare values locally without printing them.
- Pattern checks found no private keys, provider access tokens, cloud access-key identifiers, JWTs or credential-bearing HTTP URLs in the reviewed snapshot. The literal `ollama` API key is a documented local-service placeholder, not an account credential.

## PDF and image inspection

The thesis was checked through extracted text, document metadata, an attachment inventory and a visual overview of all 93 pages. No personal email address, machine home path, labeled phone/address/identity-document data, JavaScript or embedded attachment was detected. Academic attribution remains, as requested; the PDF was not modified.

Image metadata in the vendored assets was reviewed for project-specific identifiers and GPS information. No project-specific personal data or GPS information was detected. Upstream software timestamps and image-format metadata were retained.

## Publication checks

The staged publication selection is checked for sensitive filenames, local credential values and common secret patterns. The generated source archive is checked against that selection. Private audit material, comparison values, backups and temporary staging metadata remain under the ignored `.local/` directory.

Commit metadata must also use a GitHub `noreply` email. The main checkout has an empty, read-only `.git` directory, so the remote was reviewed through a separate local clone. The remote reviewed before publication had four commits. Their author and committer metadata contain the project author's personal mailbox, and an older `prompt_manager.py` contains a machine-specific home path. No local credential values or recognized access-token patterns were found in the ten historical file versions.

The prepared publication branch sanitizes those four commits while retaining their academic author names, original dates, messages and parent order, then adds the prepared release snapshot. Only the personal mailbox and local path are removed from the historical content/metadata. The author explicitly authorized replacing `main` with this sanitized history and the release snapshot, using a force-with-lease check against the reviewed remote tip. The final selection excludes `.local/`, `.pixi/`, `.vscode/`, `archive/` and the alternative spelling `archieve/`. Rewriting a branch also cannot retract copies already downloaded or guarantee removal from hosting caches and other retained references.

Source/configuration/link checks, the existing 24 unit tests and project lint checks are rerun after the corrections. Experimental data and the behavior prompt remain unchanged.

## Limits

No automated or manual review guarantees the absence of all sensitive information. Pattern matching can miss unknown credential formats, and a page overview cannot establish that every pixel of an embedded screenshot is free of sensitive text. This review covers the currently advertised branch history; it does not cover unreachable objects, hosting caches, other people's copies, server-side settings, model-service accounts or software vulnerabilities. A clean result applies to the reviewed snapshot only; later changes require another check.
