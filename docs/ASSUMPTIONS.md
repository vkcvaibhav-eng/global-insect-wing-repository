# Version 0.1 Assumptions

1. The initial taxonomic unit is a genus-level `Taxon`; optional specimen-level
   species text does not change the assigned genus or landmark template.
2. Each student has at most one active genus assignment in Version 0.1. An
   assignment names an exact published template version, not merely a genus.
3. One specimen has one uploaded right-forewing image in this milestone.
   Additional views or replacement images are new immutable image records in a
   later version, not overwrites.
4. Accession serials are allocated independently within each stable genus code
   and begin at `000001`.
5. Submitted coordinate sets are scientific records. They are immutable;
   returned work is revised by cloning it into a new annotation revision.
6. Draft edits and deleted draft clicks are working state, not repository
   records. Every submitted, returned, and approved coordinate set is retained.
7. Reviewers may not review their own annotations. Administrators can access
   review tools but remain subject to the same contributor-separation rule.
8. Images are digitized in their encoded raster orientation. Version 0.1 does
   not silently apply EXIF rotation, crop, deskew, or resample originals.
9. Physical scale calibration is image-specific. It is computed from a known
   reference length and two clicked endpoints on that image; raw pixel and
   normalized coordinates remain preserved even when millimeter coordinates are
   derived.
10. The sample wing image is a synthetic demonstration drawing, explicitly not
   a taxonomic reference specimen.
11. SQLite supports a local, low-concurrency demonstration only. PostgreSQL is
    required for concurrent or production use.
12. CSV and TPS exports contain approved repository records only and are split
    or filtered by one exact landmark-template version. Cross-version export is
    rejected rather than combined automatically.
13. Student self-signup uses email/password only. Version 0.1 does not send
    verification email or implement Google OAuth; administrator approval is the
    account activation gate.
14. Authentication is suitable for a local milestone demonstration. Production
    deployment requires HTTPS, institutional account lifecycle controls,
    rate-limiting, session hardening, backups, and security review.
15. Machine learning, automated landmark detection, WingSearch, generalized
    Procrustes analysis, and PCA are outside Version 0.1.
