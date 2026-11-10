# Printer Issues

## Printer shows offline
1. Check that the printer is powered on and shows no error on its screen.
2. Print a configuration page from the printer menu and confirm it has an IP address on the office network.
3. On the user's computer, remove the printer and add it again from Settings > Bluetooth & devices > Printers & scanners.
4. Restart the Print Spooler service if jobs are stuck: open Services, find Print Spooler, and choose Restart.

## Jobs stuck in the queue
Stop the Print Spooler service, delete the files in C:\Windows\System32\spool\PRINTERS, then start the service again. This clears every stuck job on that computer.

## Scan to email not working
Scan to email uses an SMTP relay. If scans stopped for everyone at once, the relay password or the Microsoft 365 connector may have changed, so escalate to Tier 2. If only one user is affected, check that their email address is spelled correctly in the printer address book.
