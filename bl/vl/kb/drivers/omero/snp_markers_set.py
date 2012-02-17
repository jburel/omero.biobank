# BEGIN_COPYRIGHT
# END_COPYRIGHT

import numpy as np

import bl.vl.utils.np_ext as np_ext
from utils import make_unique_key
import wrapper as wp

from genotyping import Marker


class SNPMarkersSet(wp.OmeroWrapper):

  OME_TABLE = 'SNPMarkersSet'

  __fields__ = [('label', wp.STRING, wp.REQUIRED),
                ('maker', wp.STRING, wp.REQUIRED),
                ('model', wp.STRING, wp.REQUIRED),
                ('release', wp.STRING, wp.REQUIRED),
                ('markersSetVID', wp.VID, wp.REQUIRED),
                ('snpMarkersSetUK', wp.STRING, wp.REQUIRED)]

  MAX_LEN = 10**8
  MAX_GENOME_LEN = 10**10

  @staticmethod
  def compute_global_position(p):
    return p[0]*SNPMarkersSet.MAX_GENOME_LEN + p[1]

  @staticmethod
  def define_range_selector(mset, gc_range, closed_interval=True):
    """
    Returns a numpy array with the indices of the markers of mset that
    are contained in the provided gc_range. A gc_range is a two
    elements tuple, with each element a tuple (chromosome,
    position), where chromosome is an int in [1,26], and pos is a positive
    int. Both positional tuples should be for the same refereyesnce
    genome.  It is a responsibility of the caller to assure that mset
    has loaded markers definitions aligned on the same reference genome.

    .. code-block:: python

      ref_genome = 'hg19'
      beg_chr = 10
      beg_pos = 190000
      end_chr = 10
      end_pos = 300000

      gc_begin=(begin_chrom, begin_pos)
      gc_end  =(end_chrom, end_pos)

      ms.load_alignments(ref_genome)
      indices = kb.SNPMarkersSet.define_range_selector(
        ms,
        gc_range=(gc_begin, gc_end)
        )
      for i in indices:
        assert (beg_chr, beg_pos) <= ms.markers[i].position < (end_chr, end_pos)
    """
    if not mset.has_aligns():
      raise ValueError('aligns vector has not been loaded')
    beg, end = gc_range
    global_pos = mset.aligns['global_pos']
    idx = mset.markers['marker_indx']
    low_gpos = SNPMarkersSet.compute_global_position(beg)
    high_gpos = SNPMarkersSet.compute_global_position(end)
    sel = (low_gpos <= global_pos) &  (global_pos <= high_gpos)
    return idx[sel]

  @staticmethod
  def intersect(mset1, mset2):
    """
    Returns a pair of equal length numpy arrays where corresponding
    array elements are the indices of markers, respectively in mset1
    and mset2, that align to the same position on the same ref_genome.

    .. code-block:: python

      ref_genome = 'hg19'
      ms1.load_alignments(ref_genome)
      ms2.load_alignments(ref_genome)
      idx1, idx2 = kb.SNPMarkersSet.intersect(ms1, ms2)
      for i1, i2 in it.izip(idx1, idx2):
        assert ms1[i].position == ms2[i].position

    """
    if not (mset1.has_aligns() and mset2.has_aligns()):
      raise ValueError('both mset should be aligned')
    if mset1.ref_genome != mset2.ref_genome:
      raise ValueError('msets should be aligned to the same ref_genome')
    gpos1 = mset1.aligns['global_pos']
    gpos2 = mset2.aligns['global_pos']
    return np_ext.index_intersect(gpos1, gpos2)

  def __preprocess_conf__(self, conf):
    if not 'snpMarkersSetUK' in conf:
      conf['snpMarkersSetUK'] = make_unique_key(conf['maker'], conf['model'],
                                                conf['release'])
    return conf

  @property
  def id(self):
    return self.markersSetVID

  def has_markers(self):
    return hasattr(self, 'markers')

  def has_add_marker_info(self):
    return hasattr(self, 'add_marker_info')

  def has_aligns(self):
    return hasattr(self, 'aligns')

  def __set_markers(self, v):
    self.bare_setattr('markers', v)

  def __get_markers(self):
    return self.bare_getattr('markers')

  def __set_add_marker_info(self, v):
    self.bare_setattr('add_marker_info', v)

  def __get_add_marker_info(self, v):
    return self.bare_getattr('add_marker_info')

  def __set_aligns(self, v):
    self.bare_setattr('aligns', v)

  def __get_aligns(self):
    return self.bare_getattr('aligns')

  def get_add_marker_info_fields(self):
    if not self.has_add_marker_info():
      return ()
    return self.add_marker_info.dtype.names

  def __len__(self):
    if not self.has_markers():
      raise ValueError('markers vector has not been reloaded')
    return len(self.markers)

  def __nonzero__(self):
    return True

  def has_add_marker_info(self):
    return hasattr(self, 'add_marker_info')


  def __getitem__(self, i):
    if not self.has_markers():
      raise ValueError('markers vector has not been reloaded')
    mdef = self.markers[i]
    pos = (0, 0)
    if self.has_aligns():
      mali = self.aligns[i]
      if mali['copies'] == 1:
        pos = (mali['chromosome'], mali['pos'])
    return Marker(mdef['marker_vid'], mdef['marker_indx'],
                  pos, flip=mdef['allele_flip'])

  def load_markers(self, batch_size=1000, additional_fields=None):
    """
    Read marker info from the marker set table and store it in the
    markers attribute.

    If additional_fields is provided, it must be a list of fields from
    the marker definition table; in this case, the additional info is
    stored in the add_marker_info attribute.
    """
    data = self.proxy.gadpt.read_snp_markers_set(self.id, batch_size=batch_size)
    self.__set_markers(data)
    if additional_fields is not None:
      if "vid" not in additional_fields:
        additional_fields.append("vid")
      recs = self.proxy.get_snp_marker_definitions(col_names=additional_fields,
                                                   batch_size=batch_size)
      i1, i2 = np_ext.index_intersect(data['marker_vid'], recs['vid'])
      recs = recs[i2]
      # FIXME: this is not very efficient
      by_vid = dict((r['vid'], r) for r in recs)
      recs = np.array([by_vid[d['marker_vid']] for d in data], dtype=recs.dtype)
      self.__set_add_marker_info(recs)

  def load_alignments(self, ref_genome, batch_size=1000):
    """
    Load marker positions using known alignments on ref_genome.
    Markers that do not align will be forced to a global position
    equal to minus (marker_indx + SNPMarkersSet.MAX_LEN * omero_id of
    self). This is done to avoid ambiguities in mset intersection.
    """
    if not self.has_markers():
      raise ValueError('markers vector has not been reloaded')
    aligns = self.proxy.gadpt.read_snp_markers_set_alignments(
      self.id, batch_size=batch_size
      )
    assert len(aligns) >= len(self)
    aligns = aligns[['chromosome', 'pos', 'global_pos', 'copies']]
    aligns = aligns[:len(self)]
    no_align_positions =  - (self.markers['marker_indx'] +
                             (self.omero_id * self.MAX_LEN))
    aligns['global_pos'] = np.choose(aligns['copies'] == 1,
                                     [no_align_positions, aligns['global_pos']])
    self.bare_setattr('aligns', aligns)
    self.bare_setattr('ref_genome', ref_genome)

  def get_markers_iterator(self, indices = None):
    if not self.has_markers():
      raise ValueError('markers vector has not been reloaded')
    for i in xrange(len(self)):
      yield self[i]

  def __update_constraints__(self, base):
    uk = make_unique_key(self.maker, self.model, self.release)
    base.__setattr__(self, 'snpMarkersSetUK', uk)
