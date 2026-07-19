Apple Music Controller for Windows
===================================

Real-time key (transpose) and pitch control for the Apple Music app on
Windows. Processing applies ONLY to Apple Music - every other sound on
your PC stays untouched. Also shows the current track with a seek bar
and transport buttons.

Project page: https://github.com/frogmagical/applemusic-controller


REQUIREMENTS
------------
* Windows 10 (2004) or later / Windows 11
* Apple Music app (Microsoft Store version)
* A virtual audio cable driver, e.g. VB-CABLE (free):
  https://vb-audio.com/Cable/
  Install it with administrator rights and reboot once.
  (Any driver that provides a paired playback/recording device works.)


HOW TO USE
----------
1. Unzip anywhere and run AppleMusicController.exe
   (Windows SmartScreen may warn because the exe is unsigned;
   choose "More info" -> "Run anyway".)
2. Start playback in Apple Music.
3. In the app window:
   - Capture  : the recording side of your virtual cable
                (e.g. "CABLE Output"). Auto-selected when found.
   - Output   : the speakers/headphones you actually listen on.
   - Check "Route Apple Music to the capture cable".
     Apple Music's audio is now routed into the cable.
     Unchecking restores the Windows default device.
   - Press "Start processing".
4. Move the sliders:
   - Transpose : key change in semitones (+/-12)
   - Pitch     : fine tune in cents (+/-100)
   The seek bar and the prev/play/next buttons control Apple Music.


NOTES & LIMITATIONS
-------------------
* Tempo/speed change is not offered: Apple Music delivers audio only in
  real time (DRM-protected stream), so sustained faster-than-realtime
  playback is fundamentally impossible for a live source.
* Total latency is roughly 150 ms - fine for listening, not for video sync.
* Seek and routing rely on undocumented Windows/Apple Music internals
  and may break after major updates.
* The seek bar needs the Apple Music window to be open (not closed to tray).


This package bundles the Rubber Band Library (GPL) via pylibrb.
Source code: https://github.com/frogmagical/applemusic-controller
