SSE Mixin Improvements

## Problem

The original `AnalysisPipelineSSEMixin` had a design flaw that made it awkward to use:

- It yielded tuples `(sse_event, from_cache)` which required unpacking
- It returned the result via a return statement, but getting return values from generators requires catching `StopIteration`
- Most views just duplicated the pipeline event processing logic instead of using the mixin

## Solution

Refactored the mixin to store state as instance variables:

- `self._pipeline_result` - The analysis result object
- `self._pipeline_from_cache` - Whether result came from cache

Now the mixin yields only SSE events (not tuples) and stores the result for easy access after streaming completes.

## Before (Manual Event Processing)

```python
class MyStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
    def stream_data(self, request):
        pipeline = AnalysisPipeline(request)
        pipeline_stream = pipeline.stream_analysis(config)

        result = None
        from_cache = False

        # Manually process all events (30+ lines of boilerplate)
        for event_type, event_data in pipeline_stream:
            if event_type == EVENT_STATUS:
                message = event_data.get("message", "Processing...")
                from_cache = from_cache or "cache" in message.lower()
                yield send_sse_event(message)
            elif event_type == EVENT_DOWNLOAD:
                bytes_dl = event_data.get("bytes", 0)
                total_bytes = event_data.get("total", 0)
                if total_bytes > 0:
                    mb_dl = bytes_dl / (1024 * 1024)
                    mb_total = total_bytes / (1024 * 1024)
                    pct = int(bytes_dl / total_bytes * 100)
                    yield send_sse_event(f"Downloading: {mb_dl:.1f} / {mb_total:.1f} MB ({pct}%)")
                else:
                    yield send_sse_event("Downloading visit data...")
            elif event_type == EVENT_RESULT:
                result = event_data
                break

        # Now process the result
        if result:
            # ... do something with result ...
```

## After (Using Improved Mixin)

```python
class MyStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
    def stream_data(self, request):
        pipeline = AnalysisPipeline(request)
        pipeline_stream = pipeline.stream_analysis(config)

        # Stream all events using mixin (1 line!)
        yield from self.stream_pipeline_events(pipeline_stream)

        # Result is automatically available
        result = self._pipeline_result
        from_cache = self._pipeline_from_cache

        # Now process the result
        if result:
            # ... do something with result ...
```

## Benefits

1. **Less Code**: Reduced from ~30 lines of boilerplate to 1 line
2. **Consistent**: All streaming views now use the same pattern
3. **Maintainable**: Event processing logic is centralized in the mixin
4. **Easy to Use**: No tuple unpacking, no StopIteration handling, just `yield from` and access instance variables

## Views Updated

1. `KMCChildListStreamView` - Reduced from 30 lines to 3 lines for pipeline streaming
2. `VisitInspectorStreamView` - Removed duplicate code, now uses mixin properly
3. `GenericTimelineDataStreamView` - New view already using improved pattern
4. `KMCTimelineDataStreamView` - Inherits from generic view with improved mixin

## API

```python
class AnalysisPipelineSSEMixin:
    """Mixin for SSE views that use AnalysisPipeline."""

    def stream_pipeline_events(self, pipeline_stream):
        """
        Stream all pipeline events as SSE.

        Side Effects:
            - Sets self._pipeline_result to the analysis result
            - Sets self._pipeline_from_cache to True if from cache

        Yields:
            Formatted SSE event strings
        """
        # Handles STATUS, DOWNLOAD, and RESULT events automatically
        # Yields send_sse_event(...) for each event
        # Stores result in self._pipeline_result when done
```

## Usage Pattern

```python
class MyAnalysisStreamView(AnalysisPipelineSSEMixin, BaseSSEStreamView):
    def stream_data(self, request):
        # 1. Validate inputs
        if not opportunity_id:
            yield send_sse_event("Error", error="No opportunity selected")
            return

        try:
            # 2. Create pipeline and stream
            pipeline = AnalysisPipeline(request)
            pipeline_stream = pipeline.stream_analysis(config)

            # 3. Stream events using mixin (handles STATUS, DOWNLOAD, RESULT)
            yield from self.stream_pipeline_events(pipeline_stream)

            # 4. Access result
            result = self._pipeline_result

            # 5. Process and send completion
            if result:
                processed_data = self._process_result(result)
                yield send_sse_event("Complete", data=processed_data)
            else:
                yield send_sse_event("Error", error="No data found")

        except Exception as e:
            yield send_sse_event("Error", error=str(e))
```

## Reusability Impact

- **3 views** now share the same 50+ lines of pipeline event processing code
- **Future views** can use the mixin without duplicating any pipeline logic
- **Maintenance** only needs to happen in one place if event handling changes
