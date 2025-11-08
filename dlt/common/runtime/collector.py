import os
import sys
import logging
import time
from collections import defaultdict
from typing import (
    Any,
    ContextManager,
    Dict,
    TYPE_CHECKING,
    DefaultDict,
    NamedTuple,
    Optional,
    Union,
    TextIO,
)

if TYPE_CHECKING:
    from tqdm import tqdm
    import enlighten
    from enlighten import Counter as EnlCounter, StatusBar as EnlStatusBar, Manager as EnlManager
    from alive_progress import alive_bar
    from dlt.pipeline.trace import PipelineTrace, PipelineStepTrace
    from dlt.pipeline.typing import TPipelineStep
    from dlt.common.pipeline import SupportsPipeline
else:
    tqdm = EnlCounter = EnlStatusBar = EnlManager = Any
    PipelineTrace = PipelineStepTrace = TPipelineStep = SupportsPipeline = Any

from dlt.common import logger as dlt_logger
from dlt.common.exceptions import MissingDependencyException
from dlt.common.runtime.collector_base import Collector, TCollector


class NullCollector(Collector):
    """A default counter that does not count anything."""

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = None,
    ) -> None:
        pass

    def _start(self, step: str) -> None:
        pass

    def _stop(self) -> None:
        pass


class DictCollector(Collector):
    """A collector that just counts"""

    def __init__(self) -> None:
        self.step = None
        self.counters: DefaultDict[str, int] = None

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = None,
    ) -> None:
        assert not label, "labels not supported in dict collector"
        self.counters[name] += inc

    def _start(self, step: str) -> None:
        self.counters = defaultdict(int)

    def _stop(self) -> None:
        self.counters = None


class LogCollector(Collector):
    """A Collector that shows progress by writing to a Python logger or a console"""

    logger: Union[logging.Logger, TextIO]
    log_level: int

    class CounterInfo(NamedTuple):
        description: str
        start_time: float
        total: Optional[int]

    def __init__(
        self,
        log_period: float = 1.0,
        logger: Union[logging.Logger, TextIO] = sys.stdout,
        log_level: int = logging.INFO,
        dump_system_stats: bool = True,
    ) -> None:
        """
        Collector writing to a `logger` every `log_period` seconds. The logger can be a Python logger instance, text stream, or None that will attach `dlt` logger

        Args:
            log_period (float, optional): Time period in seconds between log updates. Defaults to 1.0.
            logger (logging.Logger | TextIO, optional): Logger or text stream to write log messages to. Defaults to stdio.
            log_level (str, optional): Log level for the logger. Defaults to INFO level
            dump_system_stats (bool, optional): Log memory and cpu usage. Defaults to True
        """
        self.step = None
        self.log_period = log_period
        self.logger = logger
        self.log_level = log_level
        self.counters: DefaultDict[str, int] = None
        self.counter_info: Dict[str, LogCollector.CounterInfo] = None
        self.messages: Dict[str, Optional[str]] = None
        if dump_system_stats:
            try:
                import psutil
            except ImportError:
                self._log(
                    logging.WARNING,
                    "psutil dependency is not installed and mem stats will not be available. add"
                    " psutil to your environment or pass dump_system_stats argument as False to"
                    " disable warning.",
                )
                dump_system_stats = False
        self.dump_system_stats = dump_system_stats
        self.last_log_time: float = None

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = None,
    ) -> None:
        counter_key = f"{name}_{label}" if label else name

        if counter_key not in self.counters:
            self.counters[counter_key] = 0
            self.counter_info[counter_key] = LogCollector.CounterInfo(
                description=f"{name} ({label})" if label else name,
                start_time=time.time(),
                total=total,
            )
            self.messages[counter_key] = None
            self.last_log_time = None
        else:
            counter_info = self.counter_info[counter_key]
            if inc_total:
                self.counter_info[counter_key] = LogCollector.CounterInfo(
                    description=counter_info.description,
                    start_time=counter_info.start_time,
                    total=counter_info.total + inc_total,
                )

        self.counters[counter_key] += inc
        if message is not None:
            self.messages[counter_key] = message
        self.maybe_log()

    def maybe_log(self) -> None:
        """Check if should report and if so, call self.on_log"""
        current_time = time.time()
        if self.last_log_time is None or current_time - self.last_log_time >= self.log_period:
            self.on_log()
            self.last_log_time = time.time()

    def _counter_to_log_line(
        self, counter_key: str, count: int, info: CounterInfo, current_time: float
    ) -> str:
        """
        Convert a single counter to a log line.
        Example:
            Resources: 0/1 (0.0%) | Time: 0.01s | Rate: 0.00/s
        """
        elapsed_time = current_time - info.start_time
        items_per_second = (count / elapsed_time) if elapsed_time > 0 else 0

        progress = f"{count}/{info.total}" if info.total else f"{count}"
        percentage = f"({count / info.total * 100:.1f}%)" if info.total else ""
        elapsed_time_str = f"{elapsed_time:.2f}s"
        items_per_second_str = f"{items_per_second:.2f}/s"
        message = (
            f"[{self.messages[counter_key]}]" if self.messages[counter_key] is not None else ""
        )

        return (
            f"{info.description}: {progress} {percentage} | Time: {elapsed_time_str} | Rate:"
            f" {items_per_second_str} {message}"
        ).strip()

    def _system_stats_to_log_line(self) -> str:
        """Convert system stats to a log line format."""
        try:
            import psutil

            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            current_mem = mem_info.rss / (1024**2)  # Convert to MB
            mem_percent = psutil.virtual_memory().percent
            cpu_percent = process.cpu_percent()
            return (
                f"Memory usage: {current_mem:.2f} MB ({mem_percent:.2f}%) | CPU usage:"
                f" {cpu_percent:.2f}%"
            )
        except ImportError:
            return "System stats unavailable (psutil not installed)"

    def dump_counters(self) -> None:
        """Dump all counters to log using the shared formatting methods."""
        current_time = time.time()
        log_lines = []

        step_header = f" {self.step} ".center(80, "-")
        log_lines.append(step_header)

        for name, count in self.counters.items():
            info = self.counter_info[name]
            log_lines.append(self._counter_to_log_line(name, count, info, current_time))

        if self.dump_system_stats:
            log_lines.append(self._system_stats_to_log_line())

        log_lines.append("")
        log_message = "\n".join(log_lines)
        if not self.logger:
            # try to attach dlt logger
            self.logger = dlt_logger.LOGGER
        self._log(self.log_level, log_message)

    def _log(self, log_level: int, log_message: str) -> None:
        if isinstance(self.logger, (logging.Logger, logging.LoggerAdapter)):
            self.logger.log(log_level, log_message)
        else:
            print(log_message, file=self.logger or sys.stdout)  # noqa

    def _start(self, step: str) -> None:
        self.counters = defaultdict(int)
        self.counter_info = {}
        self.messages = {}
        self.last_log_time = time.time()

    def _stop(self) -> None:
        self.on_log()
        self.counters = None
        self.counter_info = None
        self.messages = None
        self.last_log_time = None

    def on_log(self) -> None:
        self.dump_counters()


class OpenTelemetryCollector(LogCollector):
    """A Collector that sends metrics and traces to OpenTelemetry"""

    def __init__(
        self,
        log_period: float = 1.0,
        logger: Union[logging.Logger, TextIO] = sys.stdout,
        log_level: int = logging.INFO,
        dump_system_stats: bool = True,
        otlp_endpoint: Optional[str] = None,
        service_name: Optional[str] = None,
    ) -> None:
        """
        Collector that extends LogCollector to send metrics and traces to OpenTelemetry.

        Args:
            log_period (float, optional): Time period in seconds between log updates. Defaults to 1.0.
            logger (logging.Logger | TextIO, optional): Logger or text stream to write log messages to. Defaults to stdio.
            log_level (str, optional): Log level for the logger. Defaults to INFO level
            dump_system_stats (bool, optional): Log memory and cpu usage. Defaults to True
            otlp_endpoint (str, optional): OTLP endpoint URL. If not provided, uses OTEL_EXPORTER_OTLP_ENDPOINT env var.
            service_name (str, optional): Service name for OpenTelemetry. Defaults to None.
        """
        super().__init__(log_period, logger, log_level, dump_system_stats)
        self.otlp_endpoint = otlp_endpoint
        self.service_name = service_name
        self._tracer = None
        self._meter = None
        self._current_transaction = None
        self._span_stack = []
        self._counter_instruments: Dict[str, Any] = {}
        self._initialized = False

    def _ensure_initialized(self, pipeline: SupportsPipeline) -> None:
        """Initialize OpenTelemetry if not already done"""
        if self._initialized:
            return

        try:
            from opentelemetry import trace, metrics
            from opentelemetry.trace import SpanKind, Status, StatusCode
            from dlt.common.runtime.opentelemetry import init_opentelemetry

            # Get runtime config from pipeline
            runtime_config = pipeline.run_context.runtime_config

            # Initialize OpenTelemetry
            init_opentelemetry(
                runtime_config,
                service_name=self.service_name,
                otlp_endpoint=self.otlp_endpoint,
            )

            self._tracer = trace.get_tracer(__name__)
            self._meter = metrics.get_meter(__name__)
            self._initialized = True
        except Exception as e:
            dlt_logger.warning(f"Failed to initialize OpenTelemetry: {e}")
            self._initialized = False

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = None,
    ) -> None:
        """Update counter and send metric to OpenTelemetry"""
        # Call parent to maintain logging behavior
        super().update(name, inc, total, inc_total, message, label)

        # Send metrics to OpenTelemetry if initialized
        if self._initialized and self._meter:
            try:
                counter_key = f"{name}_{label}" if label else name

                # Get or create counter instrument
                if counter_key not in self._counter_instruments:
                    # Create a counter metric
                    counter = self._meter.create_counter(
                        name=f"dlt.{name}",
                        description=f"Counter for {name}",
                        unit="1",
                    )
                    self._counter_instruments[counter_key] = counter

                # Record the increment
                counter = self._counter_instruments[counter_key]
                attributes = {}
                if label:
                    attributes["label"] = label
                if message:
                    attributes["message"] = message
                if total is not None:
                    attributes["total"] = total

                counter.add(inc, attributes)
            except Exception as e:
                dlt_logger.warning(f"Failed to send metric to OpenTelemetry: {e}")

    def on_start_trace(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Start a new trace transaction"""
        self._ensure_initialized(pipeline)
        if self._initialized and self._tracer:
            try:
                from opentelemetry.trace import SpanKind

                # Start a new transaction (root span)
                self._current_transaction = self._tracer.start_as_current_span(
                    name=step,
                    kind=SpanKind.SERVER,
                )
                self._span_stack = [self._current_transaction]

                # Add attributes
                self._current_transaction.set_attribute("pipeline_name", pipeline.pipeline_name)
                if pipeline.destination:
                    self._current_transaction.set_attribute(
                        "destination", pipeline.destination.destination_name
                    )
                if pipeline.dataset_name:
                    self._current_transaction.set_attribute("dataset_name", pipeline.dataset_name)
                self._current_transaction.set_attribute("transaction_id", trace.transaction_id)
            except Exception as e:
                dlt_logger.warning(f"Failed to start OpenTelemetry trace: {e}")

    def on_start_trace_step(
        self, trace: PipelineTrace, step: TPipelineStep, pipeline: SupportsPipeline
    ) -> None:
        """Start a new trace step (span)"""
        if self._initialized and self._tracer:
            try:
                # Start a child span for the step
                span = self._tracer.start_as_current_span(name=step)
                span.set_attribute("pipeline_name", pipeline.pipeline_name)
                if pipeline.destination:
                    span.set_attribute("destination", pipeline.destination.destination_name)
                if pipeline.dataset_name:
                    span.set_attribute("dataset_name", pipeline.dataset_name)
                span.set_attribute("transaction_id", trace.transaction_id)

                # Add to stack
                self._span_stack.append(span)
            except Exception as e:
                dlt_logger.warning(f"Failed to start OpenTelemetry trace step: {e}")

    def on_end_trace_step(
        self,
        trace: PipelineTrace,
        step: PipelineStepTrace,
        pipeline: SupportsPipeline,
        step_info: Any,
        send_state: bool,
    ) -> None:
        """End a trace step (span)"""
        if self._initialized and self._span_stack:
            try:
                from opentelemetry.trace import Status, StatusCode

                # Pop and end the current span
                span = self._span_stack.pop()
                if span:
                    # Add step info as attributes
                    if step.step_exception:
                        span.set_status(Status(StatusCode.ERROR, step.step_exception))
                    else:
                        span.set_status(Status(StatusCode.OK))

                    if step.started_at and step.finished_at:
                        elapsed = (step.finished_at - step.started_at).total_seconds()
                        span.set_attribute("elapsed_seconds", elapsed)

                    span.__exit__(None, None, None)
            except Exception as e:
                dlt_logger.warning(f"Failed to end OpenTelemetry trace step: {e}")

    def on_end_trace(
        self, trace: PipelineTrace, pipeline: SupportsPipeline, send_state: bool
    ) -> None:
        """End the trace transaction"""
        if self._initialized and self._current_transaction:
            try:
                from opentelemetry.trace import Status, StatusCode

                # End all remaining spans
                while self._span_stack:
                    span = self._span_stack.pop()
                    if span:
                        span.__exit__(None, None, None)

                # End the transaction
                if self._current_transaction:
                    if trace.finished_at and trace.started_at:
                        elapsed = (trace.finished_at - trace.started_at).total_seconds()
                        self._current_transaction.set_attribute("total_elapsed_seconds", elapsed)

                    # Check if trace failed
                    if trace.steps and trace.steps[-1].step_exception:
                        self._current_transaction.set_status(
                            Status(StatusCode.ERROR, trace.steps[-1].step_exception)
                        )
                    else:
                        self._current_transaction.set_status(Status(StatusCode.OK))

                    self._current_transaction.__exit__(None, None, None)
                    self._current_transaction = None
            except Exception as e:
                dlt_logger.warning(f"Failed to end OpenTelemetry trace: {e}")

    def _stop(self) -> None:
        """Stop collecting and flush metrics"""
        # Clear counter instruments
        self._counter_instruments.clear()
        # Call parent to maintain logging behavior
        super()._stop()


class TqdmCollector(Collector):
    """A Collector that shows progress with `tqdm` progress bars"""

    def __init__(self, single_bar: bool = False, **tqdm_kwargs: Any) -> None:
        """A Collector that uses tqdm to display counters as progress bars. Set `single_bar` to True to show just the main progress bar. Pass any config to tqdm in kwargs"""
        try:
            global tqdm
            from tqdm import tqdm
        except ModuleNotFoundError:
            raise MissingDependencyException(
                "TqdmCollector", ["tqdm"], "We need tqdm to display progress bars."
            )
        self.step = None
        self.single_bar = single_bar
        self._bars: Dict[str, tqdm[None]] = {}
        self.tqdm_kwargs = tqdm_kwargs or {}

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = "",
    ) -> None:
        key = f"{name}_{label}"
        bar = self._bars.get(key)
        if bar is None:
            if label:
                name = f"{name}[{label}]"
            if len(self._bars) == 0:
                desc = self.step + ": " + name
            else:
                # do not add any more counters
                if self.single_bar:
                    return
                desc = name
            bar = tqdm(desc=desc, total=total, leave=False, **self.tqdm_kwargs)
            bar.refresh()
            self._bars[key] = bar
        else:
            if inc_total:
                bar.total += inc_total
                bar.refresh()
        if message:
            bar.set_postfix_str(message)
        bar.update(inc)

    def _start(self, step: str) -> None:
        self._bars = {}

    def _stop(self) -> None:
        for bar in self._bars.values():
            bar.refresh()
            bar.close()
        self._bars.clear()


class AliveCollector(Collector):
    """A Collector that shows progress with `alive-progress` progress bars"""

    def __init__(self, single_bar: bool = True, **alive_kwargs: Any) -> None:
        """Collector that uses alive_progress to display counters as progress bars. Set `single_bar` to True to show just the main progress bar. Pass any config to alive_progress in kwargs"""
        try:
            global alive_bar
            from alive_progress import alive_bar

        except ModuleNotFoundError:
            raise MissingDependencyException(
                "AliveCollector",
                ["alive-progress"],
                "We need alive-progress to display progress bars.",
            )
        self.step = None
        self.single_bar = single_bar
        self._bars: Dict[str, Any] = {}
        self._bars_counts: Dict[str, int] = {}
        self._bars_contexts: Dict[str, ContextManager[Any]] = {}
        self.alive_kwargs = alive_kwargs or {}

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = "",
    ) -> None:
        key = f"{name}_{label}"
        bar = self._bars.get(key)
        if bar is None:
            if label:
                name = f"{name}[{label}]"
            if len(self._bars) == 0:
                desc = self.step + ": " + name
            else:
                # do not add any more counters
                if self.single_bar:
                    return
                desc = name
            bar = alive_bar(total=total, title=desc, **self.alive_kwargs)
            self._bars_contexts[key] = bar
            bar = self._bars[key] = bar.__enter__()
            self._bars_counts[key] = 0
        else:
            # TODO: implement once total change is supported
            pass

        # if message:
        #     bar.set_postfix_str(message)
        if inc > 0:
            bar(inc)
            self._bars_counts[key] += inc

    def _start(self, step: str) -> None:
        self._bars = {}
        self._bars_contexts = {}
        self

    def _stop(self) -> None:
        for bar in self._bars_contexts.values():
            bar.__exit__(None, None, None)
        self._bars.clear()
        self._bars_contexts.clear()
        self._bars_counts.clear()


class EnlightenCollector(Collector):
    """A Collector that shows progress with `enlighten` progress and status bars that also allow for logging."""

    _bars: Dict[str, EnlCounter]
    _manager: EnlManager
    _status: EnlStatusBar

    def __init__(self, single_bar: bool = False, **enlighten_kwargs: Any) -> None:
        """Collector that uses Enlighten to display counters as progress bars. Set `single_bar` to True to show just the main progress bar. Pass any config to Enlighten in kwargs"""
        try:
            global enlighten

            import enlighten
            from enlighten import (
                Counter as EnlCounter,
                StatusBar as EnlStatusBar,
                Manager as EnlManager,
            )
        except ModuleNotFoundError:
            raise MissingDependencyException(
                "EnlightenCollector",
                ["enlighten"],
                "We need enlighten to display progress bars with a space for log messages.",
            )
        self.step = None
        self.single_bar = single_bar
        self.enlighten_kwargs = enlighten_kwargs

    def update(
        self,
        name: str,
        inc: int = 1,
        total: int = None,
        inc_total: int = None,
        message: str = None,
        label: str = "",
    ) -> None:
        key = f"{name}_{label}"
        bar = self._bars.get(key)
        if bar is None:
            if label:
                name = f"{name}[{label}]"
            if len(self._bars) > 0 and self.single_bar:
                # do not add any more counters
                return
            bar = self._manager.counter(
                desc=name, total=total, leave=True, force=True, **self.enlighten_kwargs
            )
            bar.refresh()
            self._bars[key] = bar
        else:
            if inc_total:
                bar.total = bar.total + inc_total
        bar.update(inc)

    def _start(self, step: str) -> None:
        self._bars = {}
        self._manager = enlighten.get_manager(enabled=True)
        self._status = self._manager.status_bar(
            leave=True, justify=enlighten.Justify.CENTER, fill="="
        )
        self._status.update(step)

    def _stop(self) -> None:
        if self._status:
            self._status.close()
        for bar in self._bars.values():
            bar.refresh()
            bar.close()
        self._bars.clear()
        self._manager.stop()
        self._manager = None
        self._bars = None
        self._status = None


NULL_COLLECTOR = NullCollector()
