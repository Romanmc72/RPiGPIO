# Raspberry Pi General Purpose Input/Output
I am using this directory to store code for the Raspberry Pi 3B+ that I own wherein I take the GPIO kit and some goodies I bought on Amazon and screw around with circuits.

## Learnings
The maximum recommended draw from one of the 3.3V pins is 50 mA or 0.005 A.

Since 
```
V / I = R
```
So..
```
3.3V / 0.005A = xΩ
```
Therefore we need at least a resistance of...
```
660Ω
```
My tests utilized resistors with 1kΩ or 1000Ω, which kept the Raspberry Pi safe. Here is the [link](https://www.amazon.com/EL-CK-002-Electronic-Breadboard-Capacitor-Potentiometer/dp/B01ERP6WL4/ref=sr_1_1_sspa?crid=RC880RRMAQEU&dchild=1&keywords=rexqualis+electronics+component+fun+kit&qid=1597189328&sprefix=rex+quails+%2Caps%2C163&sr=8-1-spons&psc=1&spLa=ZW5jcnlwdGVkUXVhbGlmaWVyPUE0UENKNTc1TkFPNksmZW5jcnlwdGVkSWQ9QTAyNDU1MjAyNlk4TkY2VkdYTjk5JmVuY3J5cHRlZEFkSWQ9QTA4MzkzNjNHVjQ2SjRaVkFDVDkmd2lkZ2V0TmFtZT1zcF9hdGYmYWN0aW9uPWNsaWNrUmVkaXJlY3QmZG9Ob3RMb2dDbGljaz10cnVl) to the kit I used. Pretty cheap @ <$15!

# P.S
Follow at your own risk. No Guarantees that anything here works.
Always remember to stay safe and have fun!
