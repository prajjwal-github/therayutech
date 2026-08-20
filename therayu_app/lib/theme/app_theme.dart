import 'package:flutter/material.dart';

/// ============================================================================
///                        S I N G L E   S O U R C E   O F   T R U T H
/// ============================================================================
/// Every colour, radius, gap, shadow and text style in the app is read from
/// this file. No widget contains a literal colour.
///
/// THEME SOURCE: Therayu "Final Designs" Figma (Meditech Solutions)
/// -----------------------------------------------------------------------
/// The brand runs on exactly two colours over a dark ground:
///
///   • DEEP PETROL TEAL  — the ground of every screen, carrying a faint
///                         watermark pattern in the source frames.
///   • MUSTARD GOLD      — the signature wave, and the only colour allowed to
///                         demand attention.
///   • CYAN TEAL         — the wordmark and every interactive control.
///
/// That two-accent system maps onto clinical semantics unusually cleanly, so it
/// is used rather than bolted over:
///
///   teal  -> interactive, tracked, in-range, healthy
///   gold  -> attention, end-of-range, positioning needed
///
/// If you tweak values from a fresh Figma export, the hexes below are the only
/// place to touch. Each constant is annotated with where it appears on screen.
/// ============================================================================

class AppPalette {
  const AppPalette._();

  // --------------------------------------------------------------------------
  // BRAND — lifted from the Figma frames
  // --------------------------------------------------------------------------

  /// The deep petrol teal that grounds the splash and login headers.
  static const Color brandTeal = Color(0xFF0E3A46);

  /// One step lighter, for panels sitting on top of [brandTeal].
  static const Color brandTealLight = Color(0xFF14495A);

  /// One step deeper, for the app's outermost background.
  static const Color brandTealDeep = Color(0xFF092B34);

  /// The signature wave gold.
  static const Color brandGold = Color(0xFFD9A32B);

  /// Highlight edge of the gold wave gradient.
  static const Color brandGoldLight = Color(0xFFEFC559);

  /// Shadowed edge of the gold wave gradient (the olive tone in the frames).
  static const Color brandGoldDeep = Color(0xFFA97F1E);

  /// The "therayu" wordmark cyan-teal, and the fill of the Get OTP / Verify
  /// buttons.
  static const Color brandCyan = Color(0xFF34AFAF);

  /// Lighter cyan used for the button fills in the login frames.
  static const Color brandCyanLight = Color(0xFF62C4C3);

  // --------------------------------------------------------------------------
  // SURFACES  — the app chrome behind and around the camera feed
  // --------------------------------------------------------------------------

  /// App background. Visible on the connect screen and behind letterboxed video.
  static const Color background = brandTealDeep;

  /// Panel / HUD card fill. Drawn semi-transparent over the camera feed.
  static const Color surface = brandTeal;

  /// Raised surface: card headers, selected chips, sheet backgrounds.
  static const Color surfaceRaised = brandTealLight;

  /// Hairline borders around HUD cards and panels.
  static const Color border = Color(0xFF1F5F70);

  /// Scrim laid over the camera feed behind centred dialogs and banners.
  static const Color scrim = Color(0xD8061F26);

  /// Light surface for the lower half of the login composition.
  static const Color surfaceOnLight = Color(0xFFFFFFFF);

  // --------------------------------------------------------------------------
  // TEXT
  // --------------------------------------------------------------------------

  /// Primary readouts: angle values, big numbers, titles.
  static const Color textPrimary = Color(0xFFEAF4F5);

  /// Labels, joint names, secondary rows.
  static const Color textSecondary = Color(0xFF93B3BC);

  /// Disabled / "N/A" / "TRACKING..." placeholder text.
  static const Color textMuted = Color(0xFF5D8590);

  /// Text on a gold or cyan fill.
  static const Color textOnAccent = brandTealDeep;

  // --------------------------------------------------------------------------
  // STATUS
  // --------------------------------------------------------------------------

  /// Primary accent: joint nodes, active chips, focus rings, progress arcs.
  static const Color accent = brandCyan;

  /// Success: "Ready to Begin", in-range angles, good movement quality.
  /// A mint-teal rather than a generic green, so it belongs to the palette.
  static const Color success = Color(0xFF4FD1A5);

  /// Caution: positioning guidance, borderline quality, "SHIFTED" balance.
  /// This is the brand gold doing exactly the job it does in the Figma frames.
  static const Color warning = brandGold;

  /// Error: disconnected socket, recording dot, out-of-range angles.
  /// A terracotta red, warmed to sit beside the gold instead of fighting it.
  static const Color danger = Color(0xFFE2664C);

  // --------------------------------------------------------------------------
  // SKELETON
  //
  // The limb mapping now uses the two brand colours directly: LEFT is teal,
  // RIGHT is gold. Besides being on-brand this is the clearest possible side
  // cue, and it fixes the original renderer's inconsistency (medical_gui.py
  // used blue for the left arm but amber for the left leg, and vice versa).
  // --------------------------------------------------------------------------

  /// Spine: C7_NECK -> PELVIS_CENTER, NOSE -> C7_NECK. A gold-tinted white.
  static const Color boneSpine = Color(0xFFF2E8D5);

  /// Face links: nose/eyes/ears.
  static const Color boneFace = Color(0xFFD9B08C);

  /// Torso frame: shoulder girdle, pelvic girdle, shoulder->hip rails.
  static const Color boneTorso = Color(0xFF4FD1A5);

  /// Left arm and left leg bones.
  static const Color boneLeft = Color(0xFF46C2C1);

  /// Right arm and right leg bones.
  static const Color boneRight = Color(0xFFE0A92E);

  /// Left hand 21-joint finger skeleton.
  static const Color handLeft = Color(0xFF7FD8D7);

  /// Right hand 21-joint finger skeleton.
  static const Color handRight = Color(0xFFF0C868);

  /// Joint node core.
  static const Color jointCore = Color(0xFF8FE8E7);

  /// Joint node halo drawn under the core.
  static const Color jointGlow = brandCyan;

  /// Every bone and joint desaturates to this while framing is invalid, which is
  /// the visual counterpart of the engine's "no fake angles" safety policy.
  static const Color inactive = Color(0xFF547984);

  /// Goniometric arc sweep drawn at each joint pivot.
  static const Color arc = brandCyan;

  /// Dark casing stroked underneath every bone before the coloured line goes on
  /// top. Without it a mint or gold bone disappears against a white t-shirt or a
  /// bright window behind the patient. Tinted with the brand teal rather than a
  /// neutral black so it reads as part of the palette.
  static const Color boneCasing = Color(0xE6041A20);

  /// The same idea for goniometric arcs, slightly deeper since arcs are thinner.
  static const Color arcCasing = Color(0xD9031419);

  // --------------------------------------------------------------------------
  // GRADIENTS
  // --------------------------------------------------------------------------

  /// The gold wave fill. Runs light-to-deep across the sweep, which is what
  /// gives the Figma wave its sense of depth rather than looking like a flat band.
  static const LinearGradient goldWave = LinearGradient(
    colors: <Color>[brandGoldLight, brandGold, brandGoldDeep],
    stops: <double>[0, 0.55, 1],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  /// The teal ground behind the wave.
  static const LinearGradient tealGround = LinearGradient(
    colors: <Color>[brandTeal, brandTealDeep],
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
  );

  /// Brand lockup / logo tile fill.
  static const LinearGradient brandMark = LinearGradient(
    colors: <Color>[brandCyan, brandGold],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
}

class AppRadii {
  const AppRadii._();

  /// Chips, badges, small pills.
  static const double sm = 6;

  /// HUD cards, panels, buttons. The Figma buttons sit at a soft 8.
  static const double md = 10;

  /// Sheets, large containers, camera viewport.
  static const double lg = 20;

  /// Fully rounded.
  static const double pill = 999;

  static BorderRadius get smAll => BorderRadius.circular(sm);
  static BorderRadius get mdAll => BorderRadius.circular(md);
  static BorderRadius get lgAll => BorderRadius.circular(lg);
}

class AppGaps {
  const AppGaps._();

  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;

  /// Inset of the HUD cards from the screen edges.
  static const double screenEdge = 12;
}

class AppStrokes {
  const AppStrokes._();

  /// Hairline card / panel border.
  static const double hairline = 1;

  /// Bone line width.
  static const double bone = 3.2;

  /// Dark outline drawn under each bone so it stays legible over a bright shirt.
  static const double boneOutline = 5.6;

  /// Finger bone line width.
  static const double fingerBone = 1.6;

  /// Goniometric arc width.
  static const double arc = 2.8;

  /// Joint node radius (core) and halo radius.
  static const double jointCoreRadius = 4.2;
  static const double jointGlowRadius = 8.5;
}

class AppTheme {
  const AppTheme._();

  /// Set to your Figma typeface name after wiring assets/fonts/ in pubspec.yaml.
  /// `null` uses the platform default (Roboto on Android).
  ///
  /// The Figma frames use a rounded geometric sans for the wordmark and a
  /// standard UI sans for body copy — Poppins or Quicksand read closest if you
  /// want to match without licensing the original.
  static const String? fontFamily = null;

  /// Monospaced family for angle readouts — keeps digits from jittering as
  /// values change, which matters a lot when numbers update 20x a second.
  static const String monoFamily = 'monospace';

  // --------------------------------------------------------------------------
  // TEXT STYLES
  // --------------------------------------------------------------------------

  /// Screen / section titles.
  static const TextStyle title = TextStyle(
    fontFamily: fontFamily,
    fontSize: 20,
    fontWeight: FontWeight.w700,
    color: AppPalette.textPrimary,
    letterSpacing: -0.2,
  );

  /// The "therayu" wordmark.
  static const TextStyle wordmark = TextStyle(
    fontFamily: fontFamily,
    fontSize: 34,
    fontWeight: FontWeight.w600,
    color: AppPalette.brandCyan,
    letterSpacing: -0.8,
    height: 1.0,
  );

  /// The "Meditech Solutions" line under the wordmark.
  static const TextStyle wordmarkTag = TextStyle(
    fontFamily: fontFamily,
    fontSize: 8,
    fontWeight: FontWeight.w500,
    color: AppPalette.brandGold,
    letterSpacing: 2.4,
  );

  /// HUD card headers, e.g. "LEFT UPPER BODY".
  static const TextStyle cardHeader = TextStyle(
    fontFamily: fontFamily,
    fontSize: 10,
    fontWeight: FontWeight.w700,
    color: AppPalette.accent,
    letterSpacing: 1.1,
  );

  /// Joint name labels inside HUD cards.
  static const TextStyle label = TextStyle(
    fontFamily: fontFamily,
    fontSize: 11.5,
    fontWeight: FontWeight.w500,
    color: AppPalette.textSecondary,
    letterSpacing: 0.1,
  );

  /// Angle value readouts.
  static const TextStyle value = TextStyle(
    fontFamily: monoFamily,
    fontSize: 13,
    fontWeight: FontWeight.w700,
    color: AppPalette.textPrimary,
    letterSpacing: -0.3,
  );

  /// Large hero number, e.g. movement-quality percentage.
  static const TextStyle metricLarge = TextStyle(
    fontFamily: monoFamily,
    fontSize: 26,
    fontWeight: FontWeight.w800,
    color: AppPalette.textPrimary,
    height: 1.0,
    letterSpacing: -1,
  );

  /// Floating angle badge pinned to a joint on the skeleton.
  static const TextStyle jointBadge = TextStyle(
    fontFamily: monoFamily,
    fontSize: 10.5,
    fontWeight: FontWeight.w700,
    color: AppPalette.textPrimary,
    height: 1.1,
  );

  /// Telemetry strip: FPS, latency, mode.
  static const TextStyle telemetry = TextStyle(
    fontFamily: monoFamily,
    fontSize: 10.5,
    fontWeight: FontWeight.w600,
    color: AppPalette.textSecondary,
    letterSpacing: 0.2,
  );

  /// Guidance / clinical feedback body copy.
  static const TextStyle body = TextStyle(
    fontFamily: fontFamily,
    fontSize: 13.5,
    fontWeight: FontWeight.w500,
    color: AppPalette.textPrimary,
    height: 1.35,
  );

  /// Small print, hints, captions.
  static const TextStyle caption = TextStyle(
    fontFamily: fontFamily,
    fontSize: 11,
    fontWeight: FontWeight.w500,
    color: AppPalette.textSecondary,
    height: 1.3,
  );

  // --------------------------------------------------------------------------
  // DECORATIONS
  // --------------------------------------------------------------------------

  /// Frosted HUD card sitting over the live camera feed.
  static BoxDecoration get hudCard => BoxDecoration(
        color: AppPalette.surface.withValues(alpha: 0.84),
        borderRadius: AppRadii.mdAll,
        border: Border.all(color: AppPalette.border, width: AppStrokes.hairline),
        boxShadow: const [
          BoxShadow(color: Color(0x66041A20), blurRadius: 14, offset: Offset(0, 4)),
        ],
      );

  /// Opaque panel used on the connect screen and in bottom sheets.
  static BoxDecoration get panel => BoxDecoration(
        color: AppPalette.surface,
        borderRadius: AppRadii.lgAll,
        border: Border.all(color: AppPalette.border, width: AppStrokes.hairline),
      );

  /// Status pill. [tint] drives both the border and the wash behind the text.
  static BoxDecoration statusPill(Color tint) => BoxDecoration(
        color: tint.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(AppRadii.pill),
        border: Border.all(color: tint.withValues(alpha: 0.55), width: AppStrokes.hairline),
      );

  // --------------------------------------------------------------------------
  // MATERIAL THEME
  // --------------------------------------------------------------------------

  static ThemeData get dark {
    final base = ThemeData.dark(useMaterial3: true);

    return base.copyWith(
      scaffoldBackgroundColor: AppPalette.background,
      canvasColor: AppPalette.background,
      colorScheme: base.colorScheme.copyWith(
        brightness: Brightness.dark,
        primary: AppPalette.accent,
        onPrimary: AppPalette.textOnAccent,
        secondary: AppPalette.brandGold,
        onSecondary: AppPalette.textOnAccent,
        surface: AppPalette.surface,
        onSurface: AppPalette.textPrimary,
        error: AppPalette.danger,
        outline: AppPalette.border,
      ),
      textTheme: base.textTheme.apply(
        fontFamily: fontFamily,
        bodyColor: AppPalette.textPrimary,
        displayColor: AppPalette.textPrimary,
      ),
      dividerColor: AppPalette.border,
      iconTheme: const IconThemeData(color: AppPalette.textSecondary, size: 20),
      appBarTheme: const AppBarTheme(
        backgroundColor: AppPalette.background,
        foregroundColor: AppPalette.textPrimary,
        elevation: 0,
        centerTitle: false,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppPalette.surfaceRaised,
        hintStyle: AppTheme.caption,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppGaps.lg,
          vertical: AppGaps.md,
        ),
        border: OutlineInputBorder(
          borderRadius: AppRadii.mdAll,
          borderSide: const BorderSide(color: AppPalette.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: AppRadii.mdAll,
          borderSide: const BorderSide(color: AppPalette.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: AppRadii.mdAll,
          borderSide: const BorderSide(color: AppPalette.accent, width: 1.6),
        ),
      ),
      // The Figma CTA: light cyan fill, dark text, soft corners.
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppPalette.brandCyanLight,
          foregroundColor: AppPalette.textOnAccent,
          disabledBackgroundColor: AppPalette.surfaceRaised,
          disabledForegroundColor: AppPalette.textMuted,
          minimumSize: const Size.fromHeight(50),
          textStyle: const TextStyle(
            fontFamily: fontFamily,
            fontSize: 15,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.2,
          ),
          shape: RoundedRectangleBorder(borderRadius: AppRadii.mdAll),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppPalette.textPrimary,
          side: const BorderSide(color: AppPalette.border),
          minimumSize: const Size.fromHeight(48),
          shape: RoundedRectangleBorder(borderRadius: AppRadii.mdAll),
        ),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) =>
            states.contains(WidgetState.selected)
                ? AppPalette.brandCyanLight
                : AppPalette.textMuted),
        trackColor: WidgetStateProperty.resolveWith((states) =>
            states.contains(WidgetState.selected)
                ? AppPalette.brandCyan.withValues(alpha: 0.35)
                : AppPalette.surfaceRaised),
        trackOutlineColor: const WidgetStatePropertyAll<Color>(AppPalette.border),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: AppPalette.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadii.lg)),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: AppPalette.surfaceRaised,
        contentTextStyle: AppTheme.body,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: AppRadii.mdAll),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppPalette.accent,
      ),
    );
  }
}

/// Maps a clinical value onto the status palette.
///
/// The engine exposes each joint's normal range (PhysiotherapyAngleEngine.
/// NORMAL_RANGES); anything at or beyond the top of that range is where a
/// physio wants their eye drawn, so it escalates teal -> gold -> terracotta.
Color statusColorForRatio(double ratio) {
  if (ratio.isNaN) return AppPalette.textMuted;
  if (ratio >= 0.98) return AppPalette.danger;
  if (ratio >= 0.85) return AppPalette.warning;
  return AppPalette.success;
}

/// Colour for a movement-quality percentage, matching the OpenCV HUD's
/// green-at-80% threshold.
Color qualityColor(double pct) {
  if (pct >= 80) return AppPalette.success;
  if (pct >= 60) return AppPalette.warning;
  return AppPalette.danger;
}
