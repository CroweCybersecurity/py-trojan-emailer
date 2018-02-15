# py-trojan-emailer
A Python implementation of TrojanEmailer.ps1

## Requirements
* Python 3.6.4

## Example Usage
### Sending an HTLM formatted email to a single individual:

```py-trojan-emailer.py -i <SMTP IP || FQDN> -f "jdoe@example.com" -d "John Doe" -s "Test Message" -m example-message.html -r jdoe@example.com```
