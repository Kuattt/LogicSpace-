# Security policy

LogicSpace 3.0.x is the first public release line. Security fixes are evaluated for the latest 3.0.x release; older snapshots are not promised maintenance.

Please do not post exploit details, credentials or private project files in a public issue. Use GitHub's **Report a vulnerability** action on the repository Security tab if it is enabled. If private vulnerability reporting is unavailable, contact the repository owner privately through their GitHub profile before sharing details. There is no public security email address configured for this project.

Imported project and HDL files are untrusted data. LogicSpace does not execute imported Python code. Optional external HDL tools run through a restricted local subprocess workflow; if the sandbox cannot run, external validation is unavailable rather than bypassing the sandbox. Update checks fetch only release metadata and source installs open the official release page for manual updates.
