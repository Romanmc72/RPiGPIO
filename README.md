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

Also watched a neat [youtube](https://www.youtube.com/watch?v=RHpo4wKo8pQ) video giving a high level overview of different components found in most circuits. This is a summary of the notes I took from that video.

Voltage, Current, Resistance
Circuit - Closed loop that carries electricity.
Current (electric) - The flow of electrons in a circuit. (Negative to positive)
Hole Current - Positive directed current. (a.k.a. “I”)

Current is in ampere (A) or “I” = charges through a current, coolants per second

Voltage (V) or “V” = Push that causes the current to flow

Resistance (Ω) or “R” - Opposes the current flowing through a circuit

OHM’s LAW
——————
V = I * R

DC / AC
Direct Current = Constant Current Flow, direct and constant voltage (battery)
Alternating Current = Current moves back and forth (wall socket)

Hz is the rate at which power frequency is going back and forth. Default is 60Hz (60 times per second)

Open Circuit - Lightswitch OFF, no flow
Short Circuit - least resistance path that skips the functionality of the circuit and simply generates heat without resistance

Battery / Power Source
Volts V
```
——(+ -)—— 
```
Resistor
Ohms Ω
```
——v^v^v^v———
```
Capacitor
Electric field
```
——-| |———
```
Inductor
Magnetic Field
```
——-mmmmm——
```
Dioide
One way circuit
```
——>|——-
```
LED
Light emitting diode
```
——>^|——
```
Transistor
Switch // amplifier
```
    /
——-<|
    \
```
Transformer
Upgrade/downgrade voltage
```
——\    /——
   3||E
——/    \——
```
# P.S
Follow at your own risk. No Guarantees that anything here works.
Always remember to stay safe and have fun!
