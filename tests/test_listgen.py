import os
import os.path as osp
import shutil
import random
from contextlib import contextmanager
import pytest
import pandas as pd
import numpy as np

import wordpool
from ramcontrol import listgen, exc


@contextmanager
def subdir(parent, name="sub"):
    path = osp.join(str(parent), name)
    os.mkdir(path)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_write_wordpool(tmpdir):
    fn = listgen.write_wordpool_txt

    # unsupported language
    with pytest.raises(exc.LanguageError):
        fn(tmpdir, "DA")

    # missing rec words for supported language
    with pytest.raises(exc.LanguageError):
        fn(tmpdir, "SP", True)

    # writing without lures
    with subdir(tmpdir) as path:
        ret = fn(path, "EN")
        assert len(os.listdir(path)) == 1
        assert len(ret) == 1
        assert ret[0] == osp.join(path, "RAM_wordpool.txt")

        with open(ret[0]) as f:
            words = pd.Series([l.strip() for l in f.readlines()])
            assert (words == wordpool.load("ram_wordpool_en.txt").word).all()

    # Writing with lures
    with subdir(tmpdir) as path:
        ret = fn(path, "EN", True)
        assert len(os.listdir(path)) == 2
        assert len(ret) == 2
        assert ret[0] == osp.join(path, "RAM_wordpool.txt")
        assert ret[1] == osp.join(path, "RAM_lurepool.txt")

        # targets
        with open(ret[0]) as f:
            words = pd.Series([l.strip() for l in f.readlines()])
            assert (words == wordpool.load("ram_wordpool_en.txt").word).all()

        # lures
        with open(ret[1]) as f:
            words = pd.Series([l.strip() for l in f.readlines()])
            assert (words == wordpool.load("REC1_lures_en.txt").word).all()


class TestFR:
    def test_generate_session_pool(self):
        # Test basic things like types and lengths being correct
        for language in "EN", "SP":
            session = listgen.fr.generate_session_pool(language=language)
            assert type(session) is pd.DataFrame
            assert len(session.word) == 26*12

            for listno in session.listno.unique():
                df = session[session.listno == listno]
                assert type(df) is pd.DataFrame
                assert len(df) is 12

        with pytest.raises(AssertionError):
            listgen.fr.generate_session_pool(13)
            listgen.fr.generate_session_pool(num_lists=random.randrange(26))
            listgen.fr.generate_session_pool(language="DA")

        # Test uniqueness
        session1 = listgen.fr.generate_session_pool()
        session2 = listgen.fr.generate_session_pool()
        for n in session1.listno.unique():
            first = session1[session1.listno == n]
            second = session2[session2.listno == n]
            assert not (first.word == second.word).all()  # practice lists should be shuffled, too!

    def test_assign_list_types(self):
        session = listgen.fr.generate_session_pool()
        session = listgen.assign_list_types(session, 3, 7, 11, 4)
        words_per_list = 12

        grouped = session.groupby("type")
        counts = grouped.count()
        assert len(counts.index) == 5
        assert counts.loc["PRACTICE"].listno / words_per_list == 1
        assert counts.loc["BASELINE"].listno / words_per_list == 3
        assert counts.loc["NON-STIM"].listno / words_per_list == 7
        assert counts.loc["STIM"].listno / words_per_list == 11
        assert counts.loc["PS"].listno / words_per_list == 4

        assert all(session[session["type"] == "PRACTICE"].listno == 0)

        for n in range(1, 4):
            assert n in session[session["type"] == "BASELINE"].listno.unique()

        for n in range(4, 8):
            assert n in session[session["type"] == "PS"].listno.unique()

        for n in range(8, 26):
            assert session[session.listno == n]["type"].isin(["STIM", "NON-STIM"]).all()

    def test_generate_rec1_blocks(self):
        pool = listgen.fr.generate_session_pool()
        assigned = listgen.assign_list_types(pool, 3, 6, 16, 0)
        lures = wordpool.load("REC1_lures_en.txt")
        blocks = listgen.generate_rec1_blocks(assigned, lures)

        assert isinstance(blocks, pd.DataFrame)
        assert not all([s == u for s, u in zip(sorted(blocks.listno), blocks.listno)])

        blocks2 = listgen.generate_rec1_blocks(assigned, lures)
        for n in range(len(blocks.word)):
            if blocks.word.iloc[0] != blocks2.word.iloc[0]:
                break
        assert n < len(blocks.word)

        # this should be the original index before being reset
        assert "index" in blocks.columns


class TestCatFR:
    @property
    def catpool(self):
        return wordpool.load("ram_categorized_en.txt")

    def test_assign_word_numbers(self):
        # categories are balanced
        with pytest.raises(AssertionError):
            df = pd.DataFrame({
                "word": ["a", "b", "c"],
                "category": ["cat1", "cat1", "cat2"]
            })
            listgen.catfr.assign_word_numbers(df)

        pool = listgen.catfr.assign_word_numbers(self.catpool)
        assert len(pool.word.unique()) == 300
        assert "category" in pool.columns
        assert "category_num" in pool.columns
        assert "word" in pool.columns
        assert "wordno" in pool.columns

        # check word, category numbers assigned correctly
        for cat in pool.category:
            for n, row in pool[pool.category == cat].reset_index().iterrows():
                assert n == row.wordno
        assert [(pool.category_num[pool.category == cat] == n).all()
                for n, cat in enumerate(sorted(pool.category.unique()))]

    def test_assign_list_numbers(self):
        # must assign word numbers first
        with pytest.raises(AssertionError):
            listgen.catfr.assign_list_numbers(self.catpool)

        pool = listgen.catfr.assign_word_numbers(self.catpool)
        assigned = listgen.catfr.assign_list_numbers(pool)

        assert len(assigned) == 300
        assert len(assigned.word.unique()) == 300
        assert "listno" in assigned.columns
        assert len(assigned[assigned.listno < 0]) == 0
        counts = assigned.groupby("listno").listno.count()
        for count in counts:
            assert counts[count] == 12

    def test_sort_pairs(self):
        pool = self.catpool.copy()
        with pytest.raises(AssertionError):
            listgen.catfr.sort_pairs(pool)
            listgen.catfr.sort_pairs(listgen.catfr.assign_word_numbers(pool))

        pool = listgen.catfr.sort_pairs(listgen.catfr.assign_list_numbers(
            listgen.catfr.assign_word_numbers(pool)))

        # check uniqueness and that all words/categories are used
        assert len(pool.word.unique()) == 300
        assert len(pool.category.unique()) == 25

        # check that words come in pairs
        for n in pool.index[::2]:
            assert pool.category[n] == pool.category[n + 1]

        # check that last middle categories don't repeat
        for n in range(5, len(pool), 12):
            assert pool.category[n] != pool.category[n + 1]

    def test_generate_cat_session_pool(self):
        with pytest.raises(exc.LanguageError):
            listgen.catfr.generate_session_pool(language="DA")

        pool = listgen.catfr.generate_session_pool()
        assert len(pool) == 312
        assert "listno" in pool
        assert "category" in pool
        assert not any(pool.category.isnull())

        # no repeated words and all words used
        assert len(pool.word.unique()) == 312

        # all categories used
        assert len(pool.category.unique()) == 26

        # uniqueness
        pool2 = listgen.catfr.generate_session_pool()
        for n in pool.listno.unique():
            first = pool[pool.listno == n]
            second = pool2[pool2.listno == n]
            assert not (first.word == second.word).all()


class TestPAL:

    @staticmethod
    def equal_pairs(a, b):
        backward = np.array(
            [(b.loc[b.word2 == a.loc[i].word1].word1 == a.loc[i].word2).any()
             for i in a.index]).astype(np.bool)
        forward = np.array(
            [(b.loc[b.word1 == a.loc[i].word1].word2 == a.loc[i].word2).any()
             for i in a.index]).astype(np.bool)
        return backward | forward

    def test_generate_session_pool(self):
        with pytest.raises(AssertionError):
            listgen.pal.generate_n_session_pairs(1,n_pairs=8)
            listgen.pal.generate_n_session_pairs(1,n_lists=20)
        with pytest.raises(KeyError):
            listgen.pal.generate_n_session_pairs(1,language='HE')

        pool = listgen.pal.generate_n_session_pairs(1)[0]

        for field in ['word1','word2','listno','type']:
            assert field in pool.columns

        practice_pairs = pool.loc[pool.type=='PRACTICE']
        assert len(practice_pairs)*2 == np.unique(practice_pairs[['word1','word2']].values).size

        assert len(pool)*2 == np.unique(pool[['word1','word2']].values).size

        for _,list_pairs in pool.groupby('listno'):
            assert len(list_pairs)==6

    def test_assign_cue_position(self):
        pool = listgen.pal.generate_n_session_pairs(1)[0]
        cue_positions_by_list = [listgen.pal.assign_cues(words) for _,words in pool.groupby('listno')]
        for list_cue_positions in cue_positions_by_list:
            assert sum([x=='word1' for x in list_cue_positions])==len(list_cue_positions)/2
            assert sum([x=='word2' for x in list_cue_positions])==len(list_cue_positions)/2

    def test_assigned_cue_positions(self):
        pool=listgen.pal.generate_n_session_pairs(1)[0]

        for _,words_by_list in pool.groupby('listno'):
            assert (words_by_list['cue_pos']=='word1').sum()==len(words_by_list)/2
            assert (words_by_list['cue_pos']=='word2').sum()==len(words_by_list)/2

    def test_assign_balanced_list_types(self):
        pool = listgen.pal.generate_n_session_pairs(1)[0]
        pool = listgen.assign_balanced_list_types(pool,3,11,11,0,2)
        stim_period = pool.loc[(pool.type=="STIM") | (pool.type=="NON-STIM")]
        first_half = stim_period.iloc[:len(stim_period)/2]
        second_half = stim_period.iloc[len(stim_period)/2:]
        assert (stim_period.listno.values>3).all()
        assert abs((first_half.type=="STIM").sum()-(first_half.type=="NON-STIM").sum())<2*6
        assert abs((second_half.type=="STIM").sum() == (second_half.type=="NON-STIM").sum())<2*6

    # def test_make_unique_1(self):
    #
    #
    #     pool1 = pd.DataFrame(data=[['HELLO','WORLD'],['PY','CHARM'],['GREEN','DAY'],['FINAL','FANTASY']],columns=['word1','word2'])
    #     pool2 = pd.DataFrame(data=[['HELLO','CHARM'],['FANTASY','PY'],['WORLD','FINAL'],['DAY','GREEN']],columns=['word1','word2'])
    #     pool3 = pd.DataFrame(data=[['DAY','GREEN'],['WORLD','PY'],['HELLO','FANTASY'],['CHARM','FINAL']],columns=['word1','word2'])
    #
    #     assert self.equal_pairs(pool1,pool2).any()
    #     assert self.equal_pairs(pool1,pool3).any()
    #     assert self.equal_pairs(pool2,pool3).any()
    #
    #     wordpools = [pool1,pool2,pool3]
    #
    #     listgen.pal.make_unique(wordpools)
    #
    #     assert not self.equal_pairs(pool1,pool2).any()
    #     assert not self.equal_pairs(pool1,pool3).any()
    #     assert not self.equal_pairs(pool2,pool3).any()
    #
    #
    def test_uniqueness(self):
        wordpools = listgen.pal.generate_n_session_pairs(10)
        for i in range(10):
            for j in range(i):
                pool1 = wordpools[i]
                pool2 = wordpools[j]
                assert not self.equal_pairs(pool1.loc[pool1.type != 'PRACTICE'],pool2.loc[pool2.type != 'PRACTICE']).any()
    #
    #
    #
    #
    #
    #








