## Comprehensive Micro-Unit Plan

Following the micro-unit rules (≤150 LOC per module, one per Act cycle), here's the structured plan:

### **Phase 1: System Audio Capture Enhancement (Modules 6-9)**

**Module 6: System Audio Capture Handler** 
- **Purpose**: Browser-based system audio capture via `getDisplayMedia()` API
- **Scope**: ≤150 LOC for capturing screen audio, converting to proper format, chunking
- **Key Functions**: `captureSystemAudio()`, `processAudioStream()`, `formatAudioChunk()`
- **Tests**: Audio stream simulation, format conversion, error handling

**Module 7: Audio Source Manager**
- **Purpose**: Unified interface for switching between microphone/system audio/both sources  
- **Scope**: ≤150 LOC for source selection, stream management, source switching
- **Key Functions**: `AudioSourceManager`, `switchSource()`, `combineSources()`
- **Tests**: Source switching scenarios, combined audio handling, error states

**Module 8: Audio Mixing Controller** 
- **Purpose**: Control original vs translated audio playback (volume, muting, delay compensation)
- **Scope**: ≤150 LOC for audio mixing, volume control, synchronization
- **Key Functions**: `AudioMixer`, `setVolumeLevels()`, `synchronizePlayback()`
- **Tests**: Volume mixing, sync timing, playback scenarios

**Module 9: Meeting Audio Latency Monitor**
- **Purpose**: Specialized latency tracking for meeting scenarios (longer sessions, multiple speakers)
- **Scope**: ≤150 LOC extending existing LatencyMonitor for meeting-specific metrics
- **Key Functions**: `MeetingLatencyTracker`, `trackSpeakerChanges()`, `analyzeSessionQuality()`
- **Tests**: Session-length monitoring, speaker change detection, quality metrics

### **Phase 2: Zoom-Specific Features (Modules 10-12)**

**Module 10: Meeting Audio Processor**
- **Purpose**: Optimized processing pipeline for meeting audio (speaker detection, noise handling)
- **Scope**: ≤150 LOC for meeting-specific VAD, speaker change detection, noise filtering  
- **Key Functions**: `MeetingAudioProcessor`, `detectSpeakerChange()`, `filterMeetingNoise()`
- **Tests**: Multiple speaker scenarios, noise filtering, speaker boundary detection

**Module 11: Session Recording Manager**
- **Purpose**: Record and manage translation sessions for quality analysis
- **Scope**: ≤150 LOC for session recording, playback, segment extraction
- **Key Functions**: `SessionRecorder`, `startRecording()`, `extractSegments()`
- **Tests**: Recording lifecycle, segment extraction, storage management

**Module 12: Translation Quality Logger**
- **Purpose**: Detailed logging and analysis for translation quality assessment
- **Scope**: ≤150 LOC for quality metrics, error tracking, performance analysis
- **Key Functions**: `QualityLogger`, `logTranslationMetrics()`, `generateQualityReport()`
- **Tests**: Metrics collection, report generation, error categorization

### **Phase 3: Testing & Refinement (No New Modules)**
- Integration testing with real meetings
- Performance optimization based on Module 9-12 data
- Documentation and user guides
- Iterative improvements to existing modules

## Next Steps

**For your testing scenario** (recording Russian/English speech), we should start with:

**Module 6: System Audio Capture Handler** - This will enable you to:
1. Play a Russian audio file through your speakers
2. Capture it as "system audio" 
3. Translate it to English and play alongside
4. Test both Russian→English and English→Russian

## Module 6 Detailed Specification

**Purpose**: Enable browser-based system audio capture for translation
**Target**: ≤150 LOC
**Core Functionality**:
- Use `navigator.mediaDevices.getDisplayMedia()` with audio constraints
- Convert captured audio to WebSocket-compatible format
- Handle audio chunking for real-time processing
- Integrate with existing WebSocket pipeline

**Testing Strategy**:
- Simulate various audio formats and sample rates
- Test chunking with different audio lengths
- Verify WebSocket integration
- Error handling for permission/browser compatibility