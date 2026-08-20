import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'screens/splash_screen.dart';
import 'services/session_controller.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Portrait lock. The rotation maths in CameraStreamer assumes it, and a physio
  // session has no reason to reflow mid-movement.
  await SystemChrome.setPreferredOrientations(<DeviceOrientation>[
    DeviceOrientation.portraitUp,
  ]);

  // Transparent status bar so the brand header's teal runs under it, as in the
  // Figma frames. Light icons because the ground is always dark.
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.light,
    statusBarBrightness: Brightness.dark,
    systemNavigationBarColor: AppPalette.background,
    systemNavigationBarIconBrightness: Brightness.light,
  ));

  final session = SessionController();
  await session.loadPreferences();

  // Requesting the camera now means the preview is warm by the time the user
  // finishes typing an IP, instead of showing a black rectangle on entry.
  session.initialiseCamera();

  runApp(TherayuApp(session: session));
}

class TherayuApp extends StatefulWidget {
  const TherayuApp({required this.session, super.key});

  final SessionController session;

  @override
  State<TherayuApp> createState() => _TherayuAppState();
}

class _TherayuAppState extends State<TherayuApp> {
  @override
  void dispose() {
    widget.session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Therayu',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.dark,
      home: SplashScreen(session: widget.session),
    );
  }
}
