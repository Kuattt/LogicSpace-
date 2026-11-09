# LogicSpace 3.1.0 — rights and licensing review for parent and Kazakhstan counsel

This is a preparation checklist, **not a legal opinion or an approved license**.
Do not apply a new license retroactively to v3.0.0. The existing
[`LICENSE.md`](../LICENSE.md) and [`COMMERCIAL-LICENSE.md`](../COMMERCIAL-LICENSE.md)
remain drafts until the responsible rights holder approves them after review.

## Materials whose origin and rights must be established

| Material | Evidence to collect | Open question |
| --- | --- | --- |
| Original Python code and architecture | Authorship history, contributions, any copied/adapted code, any employer/school agreements. Record which files were made with Codex assistance and whether external material was supplied. | Who may license each part and authorize distribution? |
| Icons and artwork | Source files, author, creation history, third-party inputs, relationship between SVG and PNG. | Are both logo files original, and who may license the brand artwork? |
| Screenshots | Who captured them, visible third-party content, permissions for embedded artwork. | May they be distributed on the site and in source archives? |
| Examples | Provenance of JSON circuits, HDL, Assembly, generated BIN/HEX and example documentation. | Are any examples adapted from external tutorials or projects? |
| Documentation and website content | Authors, screenshots, icons, quotes, external snippets and any contributions. | Which text and visual assets may be licensed under the proposed terms? |
| Contributions from others | Pull requests, patches, issues containing code, agreements or written permissions. | Can the proposed rights holder license all contributions on the same terms? |
| Third-party binaries | Exact PySide6/Qt, Python, OpenSSL, Microsoft and NSIS build provenance, versions, notices and source requirements. | Which notices and redistribution rights apply to the final Windows artifact? |

Git commits under `Kuattt` show the account used for commits; they are not,
by themselves, proof of exclusive ownership or parental authority.

## Questions for the parent and counsel

1. Who is the legal rights holder for the original code, examples, artwork,
   documentation and brand, and how should that be documented given the
   author's age and applicable Kazakhstan law?
2. May that person approve the **unchanged** proposed source-available grant
   for both Linux and Windows starting with v3.1.0? Which date and exact
   materials should the approval cover?
3. Are private local modifications, public GitHub forks and platform rights
   described without conflicting with GitHub's terms or applicable law?
4. Are future outside contributions covered by adequate written permission?
5. Is the commercial-licensing notice sufficiently clear that it grants no
   rights and is not a signed agreement? Who could sign any future agreement?
6. For the exact Windows binary, which Qt/PySide6 LGPLv3 route and library
   source/replacement process is acceptable? What evidence is needed for
   Microsoft runtime and other bundled DLL redistribution?
7. Are the icon, screenshots and examples cleared for the proposed license?

**Decision record to obtain before release:** identified approving party,
documented authority, approved exact license text/hash, effective new version,
asset provenance, third-party compliance review and permission to publish the
specific final artifacts. A simple repository push is not that record.
