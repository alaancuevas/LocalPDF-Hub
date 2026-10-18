# Security

## Supported versions

Only the latest 4.x release gets security fixes.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private reporting
instead: on this repository, go to **Security > Report a vulnerability**.
Include the version, your system and the steps to reproduce.

You will get an answer as soon as possible; the project is maintained by
one person, so it may take a few days. Once a fix is released, the report
can be made public with credit to you, if you want it.

## Scope

LocalPDF Hub runs a server on your own computer. Reports that matter most:

- a website or another program on the same computer able to use the app's
  server or read its files;
- a PDF, image or Word file that makes the app run code, write outside its
  temporary folder or stop responding;
- anything sent over the network without `LOCALPDF_LAN` turned on.
