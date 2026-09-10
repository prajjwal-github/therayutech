import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/records.dart';

/// ============================================================================
/// RECORDS API CLIENT
/// ============================================================================
/// Talks to the `/api` routes served by the same process as the WebSocket, so
/// there is one address to configure rather than two.
///
/// REST here rather than more WebSocket messages: patient administration is
/// request/response by nature, and putting database round trips through the
/// socket would sit them behind the video queue.
/// ============================================================================

class RecordsApiException implements Exception {
  RecordsApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class RecordsApi {
  RecordsApi({this.timeout = const Duration(seconds: 8)});

  final Duration timeout;

  /// Base http origin, derived from whatever the user typed for the socket.
  String _origin = 'http://localhost:8765';

  /// Keeps the API pointed at the same machine as the inference socket.
  ///
  /// The user only ever types one address, and they type it in socket terms
  /// ("localhost:8765", "ws://192.168.1.7:8765"). This converts whatever form
  /// they used into an http origin, so the two transports can never drift apart
  /// and point at different PCs.
  void configureFromSocketUrl(String raw) {
    var value = raw.trim();
    if (value.isEmpty) {
      _origin = 'http://localhost:8765';
      return;
    }
    value = value
        .replaceFirst(RegExp(r'^wss://'), 'https://')
        .replaceFirst(RegExp(r'^ws://'), 'http://');
    if (!value.contains('://')) value = 'http://$value';

    final uri = Uri.tryParse(value);
    if (uri == null || uri.host.isEmpty) {
      _origin = 'http://localhost:8765';
      return;
    }
    final port = uri.hasPort ? uri.port : 8765;
    _origin = '${uri.scheme}://${uri.host}:$port';
  }

  String get origin => _origin;

  Uri _uri(String path, [Map<String, dynamic>? query]) => Uri.parse('$_origin$path')
      .replace(queryParameters: query?.map((k, v) => MapEntry(k, '$v')));

  Future<dynamic> _send(Future<http.Response> Function() call) async {
    late http.Response res;
    try {
      res = await call().timeout(timeout);
    } catch (e) {
      throw RecordsApiException(
        'Cannot reach the records server at $_origin. Is it running?',
      );
    }
    if (res.statusCode >= 400) {
      String detail = res.body;
      try {
        final decoded = jsonDecode(res.body);
        if (decoded is Map && decoded['detail'] != null) {
          detail = decoded['detail'].toString();
        }
      } catch (_) {/* keep the raw body */}
      throw RecordsApiException(detail, statusCode: res.statusCode);
    }
    if (res.body.isEmpty) return null;
    return jsonDecode(res.body);
  }

  Future<dynamic> _get(String path, [Map<String, dynamic>? q]) =>
      _send(() => http.get(_uri(path, q)));

  Future<dynamic> _post(String path, [Object? body, Map<String, dynamic>? q]) =>
      _send(() => http.post(
            _uri(path, q),
            headers: const {'Content-Type': 'application/json'},
            body: body == null ? null : jsonEncode(body),
          ));

  Future<dynamic> _patch(String path, Object body) => _send(() => http.patch(
        _uri(path),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ));

  List<Map<String, dynamic>> _rows(dynamic raw) => ((raw as List?) ?? const [])
      .map((e) => Map<String, dynamic>.from(e as Map))
      .toList();

  // ---------------------------------------------------------------- health --

  /// True when the records API answers. Used to decide whether to show the
  /// patient features at all, so an older server degrades gracefully.
  Future<bool> isAvailable() async {
    try {
      final res = await http.get(_uri('/api/health')).timeout(
            const Duration(seconds: 3),
          );
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // -------------------------------------------------------------- patients --

  Future<List<Patient>> listPatients({String? search}) async {
    final raw = await _get('/api/patients',
        (search != null && search.isNotEmpty) ? {'search': search} : null);
    return _rows(raw).map(Patient.fromJson).toList();
  }

  Future<Patient> createPatient({
    required String fullName,
    String? dateOfBirth,
    String? sex,
    String? phone,
    String? notes,
  }) async {
    final raw = await _post('/api/patients', {
      'full_name': fullName,
      'date_of_birth': dateOfBirth,
      'sex': sex,
      'phone': phone,
      'notes': notes,
    });
    return Patient.fromJson(Map<String, dynamic>.from(raw as Map));
  }

  Future<Patient> updatePatient(int id, Map<String, dynamic> fields) async {
    final raw = await _patch('/api/patients/$id', fields);
    return Patient.fromJson(Map<String, dynamic>.from(raw as Map));
  }

  // ------------------------------------------------------------- catalogue --

  Future<List<Condition>> listConditions() async {
    final raw = await _get('/api/conditions');
    return _rows(raw).map(Condition.fromJson).toList();
  }

  Future<List<PlannedExercise>> conditionProtocol(int conditionId) async {
    final raw = await _get('/api/conditions/$conditionId/protocol');
    return _rows(raw).map(PlannedExercise.fromJson).toList();
  }

  // ----------------------------------------------------------- assignments --

  Future<TodaysPlan> assignCondition(int patientId, int conditionId,
      {String? notes}) async {
    final raw = await _post('/api/patients/$patientId/assign', {
      'condition_id': conditionId,
      'notes': notes,
    });
    return TodaysPlan.fromJson(Map<String, dynamic>.from(raw as Map));
  }

  Future<TodaysPlan> todaysPlan(int patientId) async {
    final raw = await _get('/api/patients/$patientId/plan');
    return TodaysPlan.fromJson(Map<String, dynamic>.from(raw as Map));
  }

  // -------------------------------------------------------------- sessions --

  Future<List<SessionRecord>> listSessions(int patientId) async {
    final raw = await _get('/api/patients/$patientId/sessions');
    return _rows(raw).map(SessionRecord.fromJson).toList();
  }

  Future<List<ExerciseResult>> sessionResults(int sessionId) async {
    final raw = await _get('/api/sessions/$sessionId');
    final map = Map<String, dynamic>.from(raw as Map);
    return _rows(map['results']).map(ExerciseResult.fromRow).toList();
  }

  Future<void> saveReported(int resultId,
      {int? painScore, int? exertionScore, String? comment}) async {
    await _post('/api/results/$resultId/reported', {
      'pain_score': painScore,
      'exertion_score': exertionScore,
      'comment': comment,
    });
  }

  // -------------------------------------------------------------- progress --

  Future<ProgressReport> progress(int patientId) async {
    final raw = await _get('/api/patients/$patientId/progress');
    return ProgressReport.fromJson(Map<String, dynamic>.from(raw as Map));
  }

  /// Renders the clinician PDF on the server and returns where it was written.
  ///
  /// The path is on the SERVER's disk, not the browser's — the report is
  /// generated by reportlab in Python. On a clinic PC those are the same
  /// machine, which is the deployment this is built for.
  Future<String> buildReport(int patientId) async {
    final raw = await _post('/api/patients/$patientId/report');
    final map = Map<String, dynamic>.from(raw as Map);
    return map['path']?.toString() ?? '';
  }
}
