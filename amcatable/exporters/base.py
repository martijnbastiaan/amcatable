###########################################################################
#          (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
#                                                                         #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Affero General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Affero General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################
import io
import concurrent.futures
from contextlib import ContextDecorator
from queue import Queue, Empty


class QueueWriter(ContextDecorator):
    def __init__(self, queue: Queue):
        self.queue = queue

    def write(self, b):
        self.queue.put(b)


class Exporter(object):
    extension = None
    content_type = None

    def dump(self, table, fo, filename_hint=None, encoding_hint="utf-8"):
        """Write contents of a amcatable to file like object. The only method the file like object
        needs to support is write, which should take bytes.

        @param fo: file like object
        @param filename_hint: some formats (such as zipped) need a filename
        @param encoding_hint: encoding for bytes resulting bytes. Doesn't do anything for binary
                              formats such as ODS, XLSX or SPSS.
        """
        raise NotImplementedError("Subclasses should implement this method.")

    def dumps(self, table, filename_hint=None, encoding_hint="utf-8") -> bytes:
        """Export amcatable and return value as bytes.

        @param filename_hint: some formats (such as zipped) need a filename
        @param encoding_hint: encoding for bytes resulting bytes. Doesn't do anything for binary
                              formats such as ODS, XLSX or SPSS.
        """
        fo = io.BytesIO()
        self.dump(table, fo, filename_hint=filename_hint, encoding_hint=encoding_hint)
        return fo.getvalue()

    def _dump_iter(self, queue: Queue, table, filename_hint=None, encoding_hint="utf-8"):
        self.dump(table, QueueWriter(queue), filename_hint=filename_hint, encoding_hint=encoding_hint)

    def dump_iter(self, table, buffer_size=20, filename_hint=None, encoding_hint="utf-8") -> [bytes]:
        """Export amcatable and return an iterator of bytes. This is particularly useful for Django,
        which supports streaming responses through iterators.

        @param buffer_size: store up to N write() message in buffer
        @param filename_hint: some formats (such as zipped) need a filename
        @param encoding_hint: encoding for bytes resulting bytes. Doesn't do anything for binary
                              formats such as ODS, XLSX or SPSS.
        """
        queue = Queue(maxsize=buffer_size)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._dump_iter, queue, table, filename_hint, encoding_hint)

            while future.running() or not queue.empty():
                try:
                    # Make sure to quit if the thread threw an error
                    yield queue.get(timeout=0.2)
                except Empty:
                    continue

            # If any exceptions occurred while running _dump_iter, the exception will be thrown
            future.result()

    def dump_http_reponse(self, table, filename=None, encoding_hint="utf-8"):
        """Render amcatable as a Django response.

        @param filename: filename to suggest to browser
        @param filename_hint: some formats (such as zipped) need a filename
        @param encoding_hint: encoding for bytes resulting bytes. Doesn't do anything for binary
                              formats such as ODS, XLSX or SPSS.
        @return: Django streaming HTTP response
        """
        from django.http.response import StreamingHttpResponse
        content = self.dump_iter(table, encoding_hint=encoding_hint, filename_hint=filename)
        response = StreamingHttpResponse(content, content_type=self.content_type)
        if filename:
            attachment = 'attachment; filename="{}.{}"'.format(filename, self.extension)
            response['Content-Disposition'] = attachment
        return response
