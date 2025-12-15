// ignore_for_file: deprecated_member_use

import 'package:flutter/material.dart';
import 'dart:math';
import 'dart:convert';
import 'package:http/http.dart' as http; // REQUIRED FOR API

void main() {
  runApp(const QuantParlayEngineApp());
}

// --- THEME ---
class QuantParlayEngineApp extends StatelessWidget {
  const QuantParlayEngineApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0E1117),
        primaryColor: const Color(0xFF00FF41),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF00FF41),
          secondary: Color(0xFF00FF41),
          surface: Color(0xFF1A1C24),
        ),
        textTheme: const TextTheme(
          bodyMedium: TextStyle(fontFamily: 'Courier'),
          titleLarge: TextStyle(fontFamily: 'Courier', fontWeight: FontWeight.bold, color: Color(0xFF00FF41)),
        ),
        inputDecorationTheme: const InputDecorationTheme(
          filled: true,
          fillColor: Colors.black,
          labelStyle: TextStyle(color: Colors.grey),
          hintStyle: TextStyle(color: Colors.white24),
          enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.white24)),
          focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: Color(0xFF00FF41))),
        ),
      ),
      home: const EngineHome(),
    );
  }
}

// --- DATA MODELS ---
class Leg {
  String id;
  String name;
  String exclGroup;
  String linkGroup;
  double oddsAmerican;
  double confidence; // 1-10
  bool active;

  Leg({
    required this.id,
    required this.name,
    this.exclGroup = '',
    this.linkGroup = '',
    this.oddsAmerican = -110,
    this.confidence = 5,
    this.active = true,
  });

  double get decimalOdds {
    if (oddsAmerican >= 100) return (oddsAmerican / 100) + 1;
    if (oddsAmerican <= -100) return (100 / oddsAmerican.abs()) + 1;
    return 1.0;
  }

  double get impliedProb => (1 / decimalOdds);
  double get myProb => confidence * 0.10;

  String toCsvString() {
    return "$name,$oddsAmerican,$confidence,$exclGroup,$linkGroup,$active";
  }

  factory Leg.fromCsvString(String csv) {
    var parts = csv.split(',');
    for (int i=0; i<parts.length; i++) parts[i] = parts[i].trim();
    return Leg(
      id: DateTime.now().microsecondsSinceEpoch.toString() + Random().nextInt(1000).toString(),
      name: parts[0],
      oddsAmerican: double.tryParse(parts[1]) ?? -110,
      confidence: double.tryParse(parts[2]) ?? 5,
      exclGroup: parts.length > 3 ? parts[3] : '',
      linkGroup: parts.length > 4 ? parts[4] : '',
      active: parts.length > 5 ? parts[5].toLowerCase() == 'true' : true,
    );
  }
}

class GeneratedParlay {
  List<Leg> legs;
  double totalOddsDec;
  double trueProb;
  double kellyStake;
  double myWager;
  double ev;
  bool isCorrelated;
  bool betPlaced;

  GeneratedParlay({
    required this.legs,
    required this.totalOddsDec,
    required this.trueProb,
    required this.kellyStake,
    required this.myWager,
    required this.ev,
    required this.isCorrelated,
    this.betPlaced = false,
  });

  String get legsLabel => legs.map((l) => l.name).join(" + ");
  String get oddsDisplay {
     if (totalOddsDec >= 2.0) return "+${((totalOddsDec - 1) * 100).toStringAsFixed(0)}";
     return "-${(100 / (totalOddsDec - 1)).toStringAsFixed(0)}";
  }
  double get potentialPayout => (myWager * totalOddsDec) - myWager;
}

// --- MAIN SCREEN ---
class EngineHome extends StatefulWidget {
  const EngineHome({super.key});

  @override
  State<EngineHome> createState() => _EngineHomeState();
}

class _EngineHomeState extends State<EngineHome> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  
  // DATA
  List<Leg> _legs = [];
  List<GeneratedParlay> _portfolio = [];
  
  // STATS STATE
  double _simAvgProfit = 0;
  double _simWinRate = 0;
  double _simBestCase = 0;
  double _simWorstCase = 0;
  bool _hasRunSim = false;

  // SCENARIO STATE
  Map<String, int> _scenarioOutcomes = {};
  double _scenarioPnL = 0.0;
  int _scenarioWins = 0;
  int _scenarioLosses = 0;

  // HEDGE STATE
  double _hedgePayoutInput = 0.0;
  double _hedgeOddsInput = -110.0;

  // SETTINGS STATE
  double _bankroll = 1000.0;
  double _kellyFraction = 0.25;
  double _minLegs = 2;
  double _maxLegs = 4;
  double _correlationBoostPct = 15.0;
  bool _sgpMode = true;
  bool _autoFillKelly = false;
  double _defaultUnit = 10.0;
  
  // API STATE
  String _apiKey = "39298e045fe53816e45b2672570ff942"; // AUTO-SET KEY
  String _selectedSport = "americanfootball_nfl";
  bool _isFetching = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 5, vsync: this);
    _tabController.addListener(() => setState(() {}));
    
    // Initial Data
    _legs = [
      Leg(id: '1', name: 'Example Team A', exclGroup: 'A', linkGroup: '', oddsAmerican: -110, confidence: 5),
      Leg(id: '2', name: 'Example Team B', exclGroup: 'A', linkGroup: '', oddsAmerican: -110, confidence: 5),
    ];
  }

  // --- API LOGIC (FANDUEL) ---
  Future<void> _fetchFanDuelOdds() async {
    setState(() => _isFetching = true);
    final url = Uri.parse('https://api.the-odds-api.com/v4/sports/$_selectedSport/odds/?regions=us&markets=h2h&bookmakers=fanduel&oddsFormat=american&apiKey=$_apiKey');
    
    try {
      final response = await http.get(url);
      
      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        List<Leg> newLegs = [];
        int count = 0;

        for (var game in data) {
          String gameId = game['id'] ?? "unknown";
          // Use last 5 chars of ID as Group ID to prevent betting both sides
          String groupId = gameId.length > 5 ? gameId.substring(gameId.length - 5) : gameId;
          
          var bookmakers = game['bookmakers'] as List;
          if (bookmakers.isNotEmpty) {
            var fanduel = bookmakers.firstWhere((b) => b['key'] == 'fanduel', orElse: () => null);
            if (fanduel != null) {
              var markets = fanduel['markets'] as List;
              var h2h = markets.firstWhere((m) => m['key'] == 'h2h', orElse: () => null);
              if (h2h != null) {
                for (var outcome in h2h['outcomes']) {
                  String name = outcome['name'];
                  double price = (outcome['price'] as num).toDouble();
                  
                  newLegs.add(Leg(
                    id: "$gameId-$name",
                    name: "$name (ML)",
                    oddsAmerican: price,
                    confidence: 5, // Default confidence
                    exclGroup: groupId, // Prevents betting both sides
                    linkGroup: groupId, // SGP Logic (Same Game)
                    active: true
                  ));
                  count++;
                }
              }
            }
          }
        }
        
        setState(() {
          _legs.addAll(newLegs);
          _isFetching = false;
        });
        Navigator.pop(context); // Close Settings
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("SUCCESS: Pulled $count odds from FanDuel")));
        _tabController.animateTo(0); // Go to Build Tab

      } else {
        throw Exception("API Error: ${response.statusCode}");
      }
    } catch (e) {
      setState(() => _isFetching = false);
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("FETCH FAILED: $e\n(Note: Web browsers may block this. Use local app.)"), backgroundColor: Colors.red));
    }
  }

  // --- MATH ENGINE ---
  double _calculateKelly(double decOdds, double winProbPercent) {
    if (decOdds <= 1) return 0.0;
    double b = decOdds - 1;
    double p = winProbPercent / 100;
    double q = 1 - p;
    double kelly = (b * p - q) / b;
    return max(0, kelly * _kellyFraction);
  }

  double _getDecimal(double usOdds) {
    if (usOdds >= 100) return (usOdds / 100) + 1;
    if (usOdds <= -100) return (100 / usOdds.abs()) + 1;
    return 1.0;
  }

  void _generateParlays() {
    setState(() {
      _portfolio.clear();
      _hasRunSim = false;
      List<Leg> activeLegs = _legs.where((l) => l.active).toList();
      
      for (int r = _minLegs.toInt(); r <= _maxLegs.toInt(); r++) {
        _getCombinations(activeLegs, r, 0, [], (combo) {
          var exclGroups = combo.where((l) => l.exclGroup.isNotEmpty).map((l) => l.exclGroup).toList();
          if (exclGroups.toSet().length != exclGroups.length) return; 

          bool isCorr = false;
          if (_sgpMode) {
             var links = combo.where((l) => l.linkGroup.isNotEmpty).map((l) => l.linkGroup).toList();
             if (links.toSet().length != links.length) isCorr = true;
          }

          double decTotal = combo.fold(1.0, (prev, elem) => prev * elem.decimalOdds);
          double rawProb = combo.fold(1.0, (prev, elem) => prev * (elem.myProb)); 
          
          double finalProb = rawProb;
          if (isCorr) finalProb *= (1 + (_correlationBoostPct / 100));
          if (finalProb > 0.99) finalProb = 0.99;

          double kellyStake = _calculateKelly(decTotal, finalProb * 100) * _bankroll;
          double actualWager = _autoFillKelly ? kellyStake : _defaultUnit;
          double ev = (finalProb * ((decTotal * actualWager) - actualWager)) - ((1 - finalProb) * actualWager);

          if (actualWager > 0) {
            _portfolio.add(GeneratedParlay(
              legs: List.from(combo),
              totalOddsDec: decTotal,
              trueProb: finalProb,
              kellyStake: kellyStake,
              myWager: actualWager,
              ev: ev,
              isCorrelated: isCorr,
            ));
          }
        });
      }
      _portfolio.sort((a, b) => b.ev.compareTo(a.ev));
    });
  }

  void _getCombinations(List<Leg> source, int k, int start, List<Leg> current, Function(List<Leg>) onFound) {
    if (current.length == k) {
      onFound(current);
      return;
    }
    for (int i = start; i < source.length; i++) {
      current.add(source[i]);
      _getCombinations(source, k, i + 1, current, onFound);
      current.removeLast();
    }
  }

  void _runMonteCarlo() {
    List<GeneratedParlay> activeBets = _portfolio.where((p) => p.betPlaced).toList();
    if (activeBets.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("No bets selected! Check 'BET?' in Portfolio.")));
      return;
    }

    List<double> results = [];
    Random rng = Random();
    Map<String, double> uniqueLegProbs = {};
    for (var p in activeBets) {
      for (var l in p.legs) uniqueLegProbs[l.name] = l.myProb;
    }

    for (int i = 0; i < 1000; i++) {
      double sessionProfit = 0;
      Map<String, bool> outcomes = {};
      uniqueLegProbs.forEach((key, prob) {
        outcomes[key] = rng.nextDouble() < prob;
      });

      for (var p in activeBets) {
        bool won = p.legs.every((l) => outcomes[l.name] == true);
        if (won) sessionProfit += p.potentialPayout; else sessionProfit -= p.myWager;
      }
      results.add(sessionProfit);
    }

    setState(() {
      _simAvgProfit = results.reduce((a, b) => a + b) / results.length;
      _simBestCase = results.reduce(max);
      _simWorstCase = results.reduce(min);
      _simWinRate = (results.where((r) => r > 0).length / results.length) * 100;
      _hasRunSim = true;
    });
  }

  // --- UI ---
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text("> QUANT_PARLAY_V31", style: TextStyle(color: Color(0xFF00FF41))),
        actions: [
          IconButton(icon: const Icon(Icons.file_download), onPressed: _showExportDialog, tooltip: "Export CSV"),
          IconButton(icon: const Icon(Icons.file_upload), onPressed: _showImportDialog, tooltip: "Import CSV"),
          IconButton(icon: const Icon(Icons.settings), onPressed: _showSettingsSheet)
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: const Color(0xFF00FF41),
          labelColor: const Color(0xFF00FF41),
          unselectedLabelColor: Colors.grey,
          isScrollable: true,
          tabs: const [
             Tab(icon: Icon(Icons.build), text: "BUILD"),
             Tab(icon: Icon(Icons.list_alt), text: "PORTFOLIO"),
             Tab(icon: Icon(Icons.science), text: "SCENARIOS"),
             Tab(icon: Icon(Icons.analytics), text: "SIMS"),
             Tab(icon: Icon(Icons.history), text: "LEDGER"),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildBuilderTab(),
          _buildPortfolioTab(),
          _buildScenarioTab(),
          _buildStatsTab(),
          _buildLedgerTab(),
        ],
      ),
      floatingActionButton: _tabController.index == 0 
        ? FloatingActionButton(
            backgroundColor: const Color(0xFF00FF41),
            child: const Icon(Icons.add, color: Colors.black),
            onPressed: _showAddLegDialog,
          ) 
        : null,
    );
  }

  // --- SCENARIO TAB ---
  Widget _buildScenarioTab() {
    List<GeneratedParlay> activeBets = _portfolio.where((p) => p.betPlaced).toList();
    if (activeBets.isEmpty) return const Center(child: Text("Place bets in Portfolio first.", style: TextStyle(color: Colors.grey)));

    Set<String> uniqueLegNames = {};
    for (var p in activeBets) {
      for (var l in p.legs) uniqueLegNames.add(l.name);
    }
    List<String> legsList = uniqueLegNames.toList();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text("STRESS TESTER", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          const Text("Manually set outcomes to see impact on your portfolio.", style: TextStyle(color: Colors.grey, fontSize: 12)),
          const SizedBox(height: 20),
          ListView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: legsList.length,
            itemBuilder: (ctx, i) {
              String name = legsList[i];
              int status = _scenarioOutcomes[name] ?? 0; // 0: Pending, 1: Win, 2: Loss
              return Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(color: const Color(0xFF1A1C24), borderRadius: BorderRadius.circular(8)),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(child: Text(name, style: const TextStyle(color: Colors.white, fontSize: 12))),
                    Row(
                      children: [
                        _buildScenarioButton(name, 1, "WIN", Colors.green, status),
                        const SizedBox(width: 8),
                        _buildScenarioButton(name, 2, "LOSS", Colors.red, status),
                      ],
                    )
                  ],
                ),
              );
            },
          ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF00FF41), foregroundColor: Colors.black),
              onPressed: () {
                double tempPnL = 0;
                int wins = 0;
                int losses = 0;
                
                for (var p in activeBets) {
                  bool isWin = true;
                  bool isLoss = false;
                  
                  for (var l in p.legs) {
                    int s = _scenarioOutcomes[l.name] ?? 0;
                    if (s == 2) { isLoss = true; isWin = false; break; }
                    if (s == 0) { isWin = false; }
                  }

                  if (isLoss) {
                    tempPnL -= p.myWager;
                    losses++;
                  } else if (isWin) {
                    tempPnL += p.potentialPayout;
                    wins++;
                  }
                }
                
                setState(() {
                  _scenarioPnL = tempPnL;
                  _scenarioWins = wins;
                  _scenarioLosses = losses;
                });
              },
              child: const Text("RUN SCENARIO"),
            ),
          ),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: Colors.black, border: Border.all(color: Colors.white24), borderRadius: BorderRadius.circular(8)),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                Column(children: [const Text("P&L", style: TextStyle(color: Colors.grey)), Text("\$${_scenarioPnL.toStringAsFixed(2)}", style: TextStyle(color: _scenarioPnL >= 0 ? const Color(0xFF00FF41) : Colors.red, fontSize: 20, fontWeight: FontWeight.bold))]),
                Column(children: [const Text("W/L", style: TextStyle(color: Colors.grey)), Text("$_scenarioWins / $_scenarioLosses", style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold))]),
              ],
            ),
          )
        ],
      ),
    );
  }

  Widget _buildScenarioButton(String legName, int val, String label, Color color, int currentStatus) {
    bool isSelected = currentStatus == val;
    return GestureDetector(
      onTap: () {
        setState(() {
          _scenarioOutcomes[legName] = isSelected ? 0 : val;
        });
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? color.withOpacity(0.2) : Colors.black,
          border: Border.all(color: isSelected ? color : Colors.grey),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(label, style: TextStyle(color: isSelected ? color : Colors.grey, fontSize: 10, fontWeight: FontWeight.bold)),
      ),
    );
  }

  // --- BUILDER TAB ---
  Widget _buildBuilderTab() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(16.0),
          child: SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF1A1C24), foregroundColor: const Color(0xFF00FF41), side: const BorderSide(color: Color(0xFF00FF41)), padding: const EdgeInsets.all(16)),
              onPressed: () { _generateParlays(); _tabController.animateTo(1); },
              icon: const Icon(Icons.memory), label: const Text("RUN GENERATOR ENGINE"),
            ),
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: _legs.length, padding: const EdgeInsets.symmetric(horizontal: 16),
            itemBuilder: (ctx, i) {
              final leg = _legs[i];
              return Dismissible(
                key: Key(leg.id),
                background: Container(color: Colors.red, alignment: Alignment.centerRight, child: const Icon(Icons.delete)),
                onDismissed: (_) => setState(() => _legs.removeAt(i)),
                child: Card(
                  color: const Color(0xFF1A1C24),
                  shape: RoundedRectangleBorder(side: BorderSide(color: Colors.white.withOpacity(0.1)), borderRadius: BorderRadius.circular(8)),
                  child: SwitchListTile(
                    activeThumbColor: const Color(0xFF00FF41),
                    title: Text(leg.name, style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                    subtitle: Text("Odds: ${leg.oddsAmerican} | Conf: ${leg.confidence}/10\nExcl: [${leg.exclGroup}] Link: [${leg.linkGroup}]", style: const TextStyle(color: Colors.grey, fontSize: 12)),
                    value: leg.active, onChanged: (val) => setState(() => leg.active = val),
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  // --- PORTFOLIO TAB ---
  Widget _buildPortfolioTab() {
    if (_portfolio.isEmpty) return const Center(child: Text("NO PARLAYS\nGo to 'BUILD' and Run Engine", textAlign: TextAlign.center, style: TextStyle(color: Colors.grey)));
    return ListView.builder(
      itemCount: _portfolio.length, padding: const EdgeInsets.all(16),
      itemBuilder: (ctx, i) {
        final parlay = _portfolio[i];
        return Container(
          margin: const EdgeInsets.only(bottom: 16), padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: const Color(0xFF1A1C24), border: Border(left: BorderSide(color: parlay.isCorrelated ? Colors.purpleAccent : const Color(0xFF00FF41), width: 4)), borderRadius: BorderRadius.circular(4)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(parlay.oddsDisplay, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white)),
                  Row(
                    children: [
                      const Text("BET?", style: TextStyle(fontSize: 12, color: Colors.grey)),
                      Checkbox(
                        value: parlay.betPlaced, activeColor: const Color(0xFF00FF41), checkColor: Colors.black,
                        onChanged: (val) { setState(() { parlay.betPlaced = val ?? false; }); },
                      ),
                    ],
                  )
                ],
              ),
              Text("WAGER: \$${parlay.myWager.toStringAsFixed(2)}", style: const TextStyle(color: Color(0xFF00FF41), fontWeight: FontWeight.bold)),
              const Divider(color: Colors.white24),
              Text(parlay.legsLabel, style: const TextStyle(color: Colors.white70)),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text("EV: \$${parlay.ev.toStringAsFixed(2)}", style: const TextStyle(color: Colors.grey, fontSize: 12)),
                  if (parlay.isCorrelated) const Text("🚀 SGP BOOST", style: TextStyle(color: Colors.purpleAccent, fontSize: 10)),
                ],
              )
            ],
          ),
        );
      },
    );
  }

  // --- LEDGER TAB ---
  Widget _buildLedgerTab() {
    List<GeneratedParlay> placedBets = _portfolio.where((p) => p.betPlaced).toList();
    if (placedBets.isEmpty) return const Center(child: Text("NO BETS PLACED.\nMark checkbox in Portfolio.", style: TextStyle(color: Colors.grey)));
    
    double totalWagered = placedBets.fold(0, (sum, p) => sum + p.myWager);
    double totalPotentialProfit = placedBets.fold(0, (sum, p) => sum + p.potentialPayout);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: const Color(0xFF1A1C24), border: Border.all(color: Colors.white24), borderRadius: BorderRadius.circular(8)),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                Column(children: [const Text("TOTAL RISK", style: TextStyle(color: Colors.grey, fontSize: 10)), Text("\$${totalWagered.toStringAsFixed(2)}", style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold))]),
                Column(children: [const Text("MAX PROFIT", style: TextStyle(color: Colors.grey, fontSize: 10)), Text("\$${totalPotentialProfit.toStringAsFixed(2)}", style: const TextStyle(color: Color(0xFF00FF41), fontSize: 18, fontWeight: FontWeight.bold))]),
              ],
            ),
          ),
          const SizedBox(height: 20),
          ListView.builder(
            shrinkWrap: true, physics: const NeverScrollableScrollPhysics(), itemCount: placedBets.length,
            itemBuilder: (ctx, i) {
               final bet = placedBets[i];
               return ListTile(
                 contentPadding: EdgeInsets.zero,
                 title: Text(bet.legsLabel, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.white, fontSize: 12)),
                 subtitle: Text("Odds: ${bet.oddsDisplay}", style: const TextStyle(color: Colors.grey, fontSize: 10)),
                 trailing: Text("\$${bet.myWager.toStringAsFixed(0)}", style: const TextStyle(color: Color(0xFF00FF41))),
               );
            }
          )
        ],
      ),
    );
  }

  // --- STATS TAB ---
  Widget _buildStatsTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text("ALPHA HUNTER", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          const Text("X: Implied Prob | Y: My Confidence", style: TextStyle(color: Colors.grey, fontSize: 10)),
          const SizedBox(height: 20),
          Center(
            child: Container(
              height: 250, width: 250,
              decoration: BoxDecoration(color: const Color(0xFF1A1C24), border: Border.all(color: Colors.white10)),
              child: CustomPaint(painter: ScatterPainter(_legs)),
            ),
          ),
          const SizedBox(height: 30),
          const Divider(color: Colors.white24),
          const Text("MONTE CARLO SIM (Selected Bets)", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          const Text("Only runs on bets checked in Portfolio.", style: TextStyle(color: Colors.grey, fontSize: 10)),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF00FF41), foregroundColor: Colors.black),
              onPressed: _runMonteCarlo,
              child: const Text("RUN SIMULATION (1000 X)"),
            ),
          ),
          const SizedBox(height: 20),
          if (_hasRunSim) ...[
            Row(children: [
                _buildStatCard("AVG PROFIT", "\$${_simAvgProfit.toStringAsFixed(2)}", _simAvgProfit > 0 ? Colors.green : Colors.red),
                const SizedBox(width: 10),
                _buildStatCard("WIN RATE", "${_simWinRate.toStringAsFixed(1)}%", Colors.blue),
            ]),
            const SizedBox(height: 10),
            Row(children: [
                _buildStatCard("BEST CASE", "\$${_simBestCase.toStringAsFixed(0)}", Colors.green),
                const SizedBox(width: 10),
                _buildStatCard("WORST CASE", "\$${_simWorstCase.toStringAsFixed(0)}", Colors.red),
            ]),
          ]
        ],
      ),
    );
  }

  Widget _buildStatCard(String title, String val, Color color) {
    return Expanded(child: Container(padding: const EdgeInsets.all(16), decoration: BoxDecoration(color: const Color(0xFF1A1C24), borderRadius: BorderRadius.circular(8)), child: Column(children: [Text(title, style: const TextStyle(color: Colors.grey, fontSize: 10)), Text(val, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 18))])));
  }

  // --- CSV / IMPORT ---
  void _showExportDialog() {
    String header = "Name,Odds,Conf,Excl,Link,Active";
    String body = _legs.map((l) => l.toCsvString()).join("\n");
    String fullCsv = "$header\n$body";
    showDialog(context: context, builder: (ctx) => AlertDialog(scrollable: true, backgroundColor: const Color(0xFF1A1C24), title: const Text("EXPORT CSV", style: TextStyle(color: Color(0xFF00FF41))), content: Column(mainAxisSize: MainAxisSize.min, children: [const Text("Copy this text and save as .csv:", style: TextStyle(color: Colors.white70)), Container(padding: const EdgeInsets.all(8), color: Colors.black, height: 150, child: SingleChildScrollView(child: SelectableText(fullCsv, style: const TextStyle(fontFamily: 'Courier', fontSize: 12, color: Colors.white))))])));
  }

  void _showImportDialog() {
    TextEditingController controller = TextEditingController();
    showDialog(context: context, builder: (ctx) => AlertDialog(scrollable: true, backgroundColor: const Color(0xFF1A1C24), title: const Text("IMPORT DATA", style: TextStyle(color: Color(0xFF00FF41))), content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [const Text("Paste CSV or Pandas Table:", style: TextStyle(color: Colors.white70, fontSize: 12)), TextField(controller: controller, maxLines: 10, style: const TextStyle(fontFamily: 'Courier', fontSize: 11, color: Colors.white), decoration: const InputDecoration(filled: true, fillColor: Colors.black, hintText: "Paste here..."))]), actions: [TextButton(child: const Text("LOAD", style: TextStyle(color: Color(0xFF00FF41))), onPressed: () {
              List<Leg> newLegs = []; List<String> lines = controller.text.split('\n');
              for (String line in lines) {
                line = line.trim(); if (line.isEmpty) continue; if (line.startsWith("Active") || line.contains("Excl Group")) continue; if (int.tryParse(line) != null) continue;
                Leg? parsed;
                if (line.contains('\t')) {
                  List<String> parts = line.split('\t'); if (parts.length >= 7) {
                    parsed = Leg(id: DateTime.now().microsecondsSinceEpoch.toString() + Random().nextInt(1000).toString(), active: parts[1].trim().toUpperCase() == 'TRUE', exclGroup: parts[2].trim(), linkGroup: parts[3].trim(), name: parts[4].trim(), oddsAmerican: double.tryParse(parts[5]) ?? -110, confidence: double.tryParse(parts[6]) ?? 5);
                  }
                } else if (line.contains(',')) { try { parsed = Leg.fromCsvString(line); } catch (e) { /* ignore */ } }
                if (parsed != null) newLegs.add(parsed);
              }
              if (newLegs.isNotEmpty) { setState(() { _legs = newLegs; }); Navigator.pop(ctx); ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text("LOADED ${newLegs.length} LEGS"))); } else { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("NO VALID DATA FOUND."))); }
            })]));
  }

  void _showAddLegDialog() {
    String name = ""; String odds = "-110"; String excl = ""; String link = ""; double conf = 5.0;
    showDialog(context: context, builder: (ctx) { return StatefulBuilder(builder: (context, setState) { return AlertDialog(scrollable: true, backgroundColor: const Color(0xFF1A1C24), title: const Text("ADD PROP", style: TextStyle(color: Color(0xFF00FF41))), content: Column(mainAxisSize: MainAxisSize.min, children: [TextField(decoration: const InputDecoration(labelText: "Leg Name"), style: const TextStyle(color: Colors.white), onChanged: (v) => name = v), const SizedBox(height: 10), TextField(decoration: const InputDecoration(labelText: "Odds"), style: const TextStyle(color: Colors.white), keyboardType: TextInputType.numberWithOptions(signed: true), onChanged: (v) => odds = v), const SizedBox(height: 10), Row(children: [Expanded(child: TextField(decoration: const InputDecoration(labelText: "Excl"), style: const TextStyle(color: Colors.white), onChanged: (v) => excl = v)), const SizedBox(width: 10), Expanded(child: TextField(decoration: const InputDecoration(labelText: "Link"), style: const TextStyle(color: Colors.white), onChanged: (v) => link = v))]), const SizedBox(height: 20), Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const Text("Confidence:", style: TextStyle(color: Colors.grey)), Text("${conf.toInt()}/10", style: const TextStyle(color: Color(0xFF00FF41), fontWeight: FontWeight.bold))]), Slider(value: conf, min: 1, max: 10, divisions: 9, onChanged: (val) { setState(() => conf = val); })]), actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text("CANCEL", style: TextStyle(color: Colors.grey))), TextButton(child: const Text("ADD", style: TextStyle(color: Color(0xFF00FF41))), onPressed: () { this.setState(() { _legs.add(Leg(id: DateTime.now().toString(), name: name.isEmpty ? "New Leg" : name, oddsAmerican: double.tryParse(odds) ?? -110, exclGroup: excl, linkGroup: link, confidence: conf)); }); Navigator.pop(ctx); })]); }); });
  }

  // --- SETTINGS SHEET ---
  void _showSettingsSheet() {
    showModalBottomSheet(context: context, isScrollControlled: true, backgroundColor: const Color(0xFF0E1117), builder: (ctx) { return StatefulBuilder(builder: (context, setSheetState) { return Container(height: MediaQuery.of(context).size.height * 0.85, padding: const EdgeInsets.all(24.0), child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [const Text("SYSTEM CONTROLS", style: TextStyle(color: Color(0xFF00FF41), fontSize: 18, fontWeight: FontWeight.bold)), IconButton(icon: const Icon(Icons.close, color: Colors.grey), onPressed: () => Navigator.pop(context))]), const Divider(color: Colors.white24),
                    
                    // FANDUEL API SECTION
                    const Text("LIVE ODDS FEED", style: TextStyle(color: Colors.grey, fontSize: 12)),
                    const SizedBox(height: 10),
                    Container(padding: const EdgeInsets.symmetric(horizontal: 10), decoration: BoxDecoration(color: Colors.black, borderRadius: BorderRadius.circular(5), border: Border.all(color: Colors.white24)), 
                      child: DropdownButtonHideUnderline(child: DropdownButton<String>(
                        dropdownColor: const Color(0xFF1A1C24), value: _selectedSport, isExpanded: true, style: const TextStyle(color: Colors.white),
                        items: const [
                          DropdownMenuItem(value: "americanfootball_nfl", child: Text("NFL")),
                          DropdownMenuItem(value: "basketball_nba", child: Text("NBA")),
                          DropdownMenuItem(value: "icehockey_nhl", child: Text("NHL")),
                          DropdownMenuItem(value: "basketball_ncaab", child: Text("NCAAB")),
                        ],
                        onChanged: (val) { setSheetState(() => _selectedSport = val!); setState(() => _selectedSport = val!); },
                    ))),
                    const SizedBox(height: 10),
                    SizedBox(width: double.infinity, child: ElevatedButton(style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF00FF41), foregroundColor: Colors.black), onPressed: _isFetching ? null : _fetchFanDuelOdds, child: _isFetching ? const CircularProgressIndicator(color: Colors.black) : const Text("PULL LIVE FANDUEL ODDS"))),
                    const Divider(color: Colors.white24, height: 30),

                    _buildSettingHeader("Bankroll", "\$${_bankroll.toStringAsFixed(0)}"), Slider(value: _bankroll, min: 100, max: 10000, onChanged: (val) { setState(() => _bankroll = val); setSheetState(() {}); }), SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text("Auto-Fill Kelly Stake", style: TextStyle(color: Colors.white)), activeColor: const Color(0xFF00FF41), value: _autoFillKelly, onChanged: (val) { setState(() => _autoFillKelly = val); setSheetState(() {}); }), if (!_autoFillKelly) ...[const Text("Default Unit Size (\$)", style: TextStyle(color: Colors.grey)), const SizedBox(height: 5), TextField(keyboardType: TextInputType.number, decoration: const InputDecoration(hintText: "e.g. 10.0"), style: const TextStyle(color: Colors.white), onChanged: (val) => _defaultUnit = double.tryParse(val) ?? 10.0), const SizedBox(height: 15)], _buildSettingHeader("Kelly Fraction", _kellyFraction.toStringAsFixed(2)), Slider(value: _kellyFraction, min: 0.1, max: 1.0, onChanged: (val) { setState(() => _kellyFraction = val); setSheetState(() {}); }), _buildSettingHeader("Min Legs", _minLegs.toInt().toString()), Slider(value: _minLegs, min: 2, max: 10, divisions: 8, onChanged: (val) { if (val <= _maxLegs) { setState(() => _minLegs = val); setSheetState(() {}); } }), _buildSettingHeader("Max Legs", _maxLegs.toInt().toString()), Slider(value: _maxLegs, min: 2, max: 15, divisions: 13, onChanged: (val) { if (val >= _minLegs) { setState(() => _maxLegs = val); setSheetState(() {}); } }), _buildSettingHeader("SGP Boost", "${_correlationBoostPct.toInt()}%"), Slider(value: _correlationBoostPct, min: 0, max: 50, onChanged: (val) { setState(() => _correlationBoostPct = val); setSheetState(() {}); }), SwitchListTile(contentPadding: EdgeInsets.zero, title: const Text("Enable SGP Logic", style: TextStyle(color: Colors.white)), activeColor: const Color(0xFF00FF41), value: _sgpMode, onChanged: (val) { setState(() => _sgpMode = val); setSheetState(() {}); }), const SizedBox(height: 40)]))); }); });
  }

  Widget _buildSettingHeader(String title, String val) { return Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [Text(title, style: const TextStyle(color: Colors.grey)), Text(val, style: const TextStyle(color: Color(0xFF00FF41), fontWeight: FontWeight.bold))]); }
}

class ScatterPainter extends CustomPainter {
  final List<Leg> legs; ScatterPainter(this.legs);
  @override
  void paint(Canvas canvas, Size size) { final paint = Paint()..color = Colors.white24..strokeWidth = 1; canvas.drawLine(Offset(0, size.height), Offset(size.width, 0), paint); final pointPaint = Paint()..strokeCap = StrokeCap.round..strokeWidth = 8; for (var leg in legs) { if (!leg.active) continue; double x = leg.impliedProb * size.width; double y = size.height - (leg.myProb * size.height); pointPaint.color = leg.myProb > leg.impliedProb ? const Color(0xFF00FF41) : Colors.redAccent; canvas.drawCircle(Offset(x, y), 5, pointPaint); } }
  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
