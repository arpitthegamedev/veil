' Veil Launcher — runs veil.py with no console window
' Place this .vbs file alongside veil.py
' Double-click to launch silently

Dim shell
Set shell = CreateObject("WScript.Shell")

' Get the folder this .vbs file is in
Dim folder
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

' Run pythonw (no console). Falls back gracefully if path is set correctly.
shell.Run "pythonw """ & folder & "veil.py""", 0, False

Set shell = Nothing
