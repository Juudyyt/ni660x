from nidaqmx.system import System
from xmlrpc.server import SimpleXMLRPCServer
import logging
import click
import yaml
from .counter import PulseCounter
from .generator import PulseTimeGenerator


# TODO Implement logs

class CountingApp:
    """
    Application to implement the acquisition on the beamline. It has
    multiples channels and one timer. The channels can be counter and/or
    encoder capture. The timer generate a periodic gate according to the
    acquisition parameters: high, low and delay.
    """

    def __init__(self, yaml_file):
        with open(yaml_file) as f:
            self.config = yaml.full_load(f)

        # Do connections
        self.system = System.local()
        term_from = self.config['connections']['from']
        terms_to = self.config['connections']['to']
        for term_to in terms_to:
            self.system.connect_terms(term_from, term_to)
            print('Connect', term_from, 'to', term_to)

        self._timer = PulseTimeGenerator(self.config['timer']['channel'])
        self._channels = {}
        self._channels_started = []
        for name, config in self.config['counters'].items():
            self._channels[name] = PulseCounter(
                config['channel'], name, config['gate'], config['source'])

        # TODO implement encoder capture

    def __del__(self):
        term_from = self.config['connections']['from']
        terms_to = self.config['connections']['to']
        for term_to in terms_to:
            self.system.disconnect_terms(term_from, term_to)
            print('Disconnect', term_from, 'to', term_to)

    def start_channels(self, samples):
        """ Method to start only the counters and encoders"""
        self._channels_started = []
        for name, channel in self._channels.items():
            channel.start(samples)
            if channel.enabled:
                self._channels_started.append(name)

    def start_timer(self, samples, high_time, low_time, initial_delay=0):
        """ Method to start only the generator"""
        self._timer.start(samples, high_time, low_time, initial_delay)

    def start_all(self, samples, high_time, low_time, initial_delay=0):
        """ Method to start first the channels and after the timer
        :param samples: number of sample to acquire
        :type int
        :param high_time: pulse high time in seconds
        :type float
        :param low_time: pulse low time in seconds
        :type float
        :param initial_delay: pulse initial delay in seconds
        :type float
        """
        self.start_channels(samples)
        self.start_timer(samples, high_time, low_time, initial_delay)

    def stop(self):
        self._timer.stop()

        for channel in self._channels.values():
            channel.stop()

        # TODO stop encoders

    def get_all_data(self):
        """
        Return a dictionary with the data acquired for all channels.  The
        length of each data can be different according to the acquisition
        state.
        :return: {str: [float]}
        """
        data = {}
        for name in self._channels_started:
            data[name] = self._channels_started[name].data.tolist()
        return data

    def get_names(self):
        """
        Return names for all counters and encoders
        :return: [str]
        """
        return list(self._channels.keys())

    def get_channel_data(self, name, start=0, end=-1):
        """
        Return channel (counter or encoder) data
        :param name: counter or encoder name
        :type str
        :param start: int start index position
        :type int
        :param end: int end index position
        :type int
        :return: [float]
        """
        data = self._channels[name].data[start:end].tolist()
        return data

    def set_channels_enabled(self, names=[], enabled=True):
        """
        Set the enabled attribute of each channel. If the channel is
        enabled it will acquire data.
        :param names: Channels names
        :type [str,]
        :param enabled: bool Enabled state for the channels
        :type bool
        :return:
        """
        if len(names) == 0:
            names = self._channels.keys()

        for name in names:
            self._channels[name].enabled = enabled

    def get_channels_enabled(self):
        """
        Return a dictionary with the value of enabled attribute for each
        channel

        :return: {str: bool}
        """
        status = {}
        for name, channel in self._channels.items():
            status[name] = channel.enabled
        return status

    def get_samples_readies(self):
        samples_readies = []
        for name in self._channels_started:
            samples_readies.append(self._channels[name].sample_readies)
        if len(samples_readies):
            return min(samples_readies)
        else:
            return 0

    def is_done(self):
        return self._timer.done


@click.command()
@click.option('-h', '--host', default='localhost', type=click.STRING)
@click.option('-p', '--port', default=9000, type=click.INT)
@click.option('--log-level', 'log_level', default=logging.INFO)
@click.argument('config', type=click.STRING)
def main(host, port, log_level, config):
    app = CountingApp(config)
    server = SimpleXMLRPCServer(('0', port), logRequests=True,
                                allow_none=True)
    server.register_introspection_functions()
    server.register_instance(app)

    try:
        print('Use Control-C to exit')
        server.serve_forever()
    except KeyboardInterrupt:
        print('Exiting...')

